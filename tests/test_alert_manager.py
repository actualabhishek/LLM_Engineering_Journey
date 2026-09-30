"""Alert manager tests with fake notifiers. No real HTTP calls, no real waiting - time is injected."""
import pytest

from app.alerts.base import Alert, Notifier
from app.alerts.manager import AlertManager

pytestmark = pytest.mark.asyncio


class FakeNotifier(Notifier):
    def __init__(self, name: str, fail: bool = False):
        self.name = name
        self.fail = fail
        self.sent: list[Alert] = []

    async def send(self, alert: Alert) -> bool:
        if self.fail:
            raise RuntimeError(f"{self.name} is down")
        self.sent.append(alert)
        return True


def make_alert(state="DOWN", target_id="rtr01"):
    return Alert(target_id=target_id, hostname="LI-MDF-IRTR-1001-01", ip="32.142.239.74", new_state=state, ts=0)


def make_manager(escalate_call_after_s=120, repeat_every_s=600, fail_channel=None):
    notifiers = {
        "telegram": FakeNotifier("telegram", fail=(fail_channel == "telegram")),
        "whatsapp": FakeNotifier("whatsapp", fail=(fail_channel == "whatsapp")),
        "ntfy": FakeNotifier("ntfy", fail=(fail_channel == "ntfy")),
        "telegram_call": FakeNotifier("telegram_call", fail=(fail_channel == "telegram_call")),
    }
    return AlertManager(notifiers, escalate_call_after_s, repeat_every_s), notifiers


async def test_on_down_sends_text_channels_but_not_call_yet():
    mgr, notifiers = make_manager()
    await mgr.on_down(make_alert(), now=1000)

    assert len(notifiers["telegram"].sent) == 1
    assert len(notifiers["whatsapp"].sent) == 1
    assert len(notifiers["ntfy"].sent) == 1
    assert len(notifiers["telegram_call"].sent) == 0  # no immediate call for a single router down


async def test_site_isolated_calls_immediately():
    mgr, notifiers = make_manager()
    await mgr.on_down(make_alert(state="SITE_ISOLATED"), now=1000, immediate_call=True)
    assert len(notifiers["telegram_call"].sent) == 1


async def test_escalates_to_call_after_threshold_if_unacked():
    mgr, notifiers = make_manager(escalate_call_after_s=120, repeat_every_s=600)
    await mgr.on_down(make_alert(), now=1000)

    await mgr.tick(now=1000 + 60)  # before threshold
    assert len(notifiers["telegram_call"].sent) == 0

    await mgr.tick(now=1000 + 120)  # at threshold
    assert len(notifiers["telegram_call"].sent) == 1


async def test_repeats_every_interval_until_acked():
    mgr, notifiers = make_manager(escalate_call_after_s=120, repeat_every_s=600)
    await mgr.on_down(make_alert(), now=1000)
    await mgr.tick(now=1000 + 120)  # escalation call
    assert len(notifiers["telegram_call"].sent) == 1

    await mgr.tick(now=1000 + 120 + 600)  # one repeat interval later
    assert len(notifiers["telegram"].sent) == 2  # initial + 1 repeat
    assert len(notifiers["telegram_call"].sent) == 2


async def test_ack_stops_repeats():
    mgr, notifiers = make_manager(escalate_call_after_s=120, repeat_every_s=600)
    await mgr.on_down(make_alert(), now=1000)
    await mgr.tick(now=1000 + 120)
    assert len(notifiers["telegram_call"].sent) == 1

    assert mgr.ack("rtr01", by="abhishek") is True
    await mgr.tick(now=1000 + 120 + 600)
    await mgr.tick(now=1000 + 120 + 1200)
    assert len(notifiers["telegram_call"].sent) == 1  # no further calls after ACK


async def test_recovery_clears_incident_and_sends_recovery_alert():
    mgr, notifiers = make_manager()
    await mgr.on_down(make_alert(), now=1000)
    await mgr.on_recovery(make_alert(state="UP"), now=1500)

    assert "rtr01" not in mgr.incidents
    assert len(notifiers["telegram"].sent) == 2  # down + recovery
    assert len(notifiers["whatsapp"].sent) == 2
    assert len(notifiers["ntfy"].sent) == 1  # ntfy is not a recovery channel


async def test_one_channel_failing_does_not_block_others():
    mgr, notifiers = make_manager(fail_channel="whatsapp")
    await mgr.on_down(make_alert(), now=1000)  # must not raise

    assert len(notifiers["telegram"].sent) == 1
    assert len(notifiers["ntfy"].sent) == 1
    assert len(notifiers["whatsapp"].sent) == 0  # failed, but did not block the others
