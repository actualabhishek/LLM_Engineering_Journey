"""Integration test for run_monitor_cycle: probe -> DB -> state machine -> alerts, wired together.

Uses a fake probe_target/probe_canaries (monkeypatched) so no real network call happens.
"""
import pytest

import app.monitor.scheduler as scheduler
from app.alerts.base import Alert, Notifier
from app.alerts.manager import AlertManager
from app.config import AppConfig, FlapConfig, ProbeConfig, Secrets, Settings, Target
from app.db import get_db
from app.monitor.prober import ProbeResult
from app.monitor.state import StateMachine
from app.runtime import RuntimeState

pytestmark = pytest.mark.asyncio


class FakeNotifier(Notifier):
    def __init__(self, name: str):
        self.name = name
        self.sent: list[Alert] = []

    async def send(self, alert: Alert) -> bool:
        self.sent.append(alert)
        return True


def make_runtime_state(conn, notifiers):
    app_cfg = AppConfig(
        site="LI-MDF",
        probe=ProbeConfig(interval_s=10, fail_threshold=3, recover_threshold=2),
        flap=FlapConfig(max_changes=4, window_s=600),
        canaries=["1.1.1.1", "8.8.8.8"],
        targets=[
            Target(id="rtr01", hostname="RTR01", ip="203.0.113.1", tcp_port=22),
            Target(id="rtr02", hostname="RTR02", ip="203.0.113.2", tcp_port=22),
        ],
    )
    settings = Settings(app=app_cfg, secrets=Secrets())
    sm = StateMachine(3, 2, 4, 600)
    am = AlertManager(notifiers, escalate_call_after_s=120, repeat_every_s=600)
    return RuntimeState(settings=settings, conn=conn, state_machine=sm, alert_manager=am)


def fake_cycle(ok: bool, rtr01_ok: bool | None = None):
    """rtr02 always OK (keeps the site from looking isolated); rtr01 follows `ok` unless overridden."""

    async def _run_probe_cycle(cfg):
        results = []
        for target_id, target_ok in (("rtr01", rtr01_ok if rtr01_ok is not None else ok), ("rtr02", True)):
            results.append(
                ProbeResult(
                    target_id=target_id, ok=target_ok, rtt_avg=10.0 if target_ok else None, rtt_min=None,
                    rtt_max=None, loss_pct=0.0 if target_ok else 100.0, jitter=None, method="icmp",
                )
            )
        return results, True  # canaries_ok=True

    return _run_probe_cycle


async def test_startup_up_transition_does_not_send_recovery_alert(tmp_path, monkeypatch):
    conn = await get_db(tmp_path / "monitor.db")
    notifiers = {"telegram": FakeNotifier("telegram"), "whatsapp": FakeNotifier("whatsapp"), "ntfy": FakeNotifier("ntfy")}
    state = make_runtime_state(conn, notifiers)

    monkeypatch.setattr(scheduler, "run_probe_cycle", fake_cycle(ok=True))
    await scheduler.run_monitor_cycle(state, now=1000)
    await scheduler.run_monitor_cycle(state, now=1010)  # 2nd OK -> UNKNOWN -> UP

    assert state.state_machine.targets["rtr01"].state == "UP"
    assert notifiers["telegram"].sent == []  # regression: no "recovered" alert on startup
    assert notifiers["whatsapp"].sent == []
    assert state.alert_manager.incidents == {}

    await conn.close()


async def test_sustained_failure_then_recovery_sends_down_then_recovery(tmp_path, monkeypatch):
    conn = await get_db(tmp_path / "monitor.db")
    notifiers = {"telegram": FakeNotifier("telegram"), "whatsapp": FakeNotifier("whatsapp"), "ntfy": FakeNotifier("ntfy")}
    state = make_runtime_state(conn, notifiers)

    monkeypatch.setattr(scheduler, "run_probe_cycle", fake_cycle(ok=True))
    await scheduler.run_monitor_cycle(state, now=1000)
    await scheduler.run_monitor_cycle(state, now=1010)  # UP

    monkeypatch.setattr(scheduler, "run_probe_cycle", fake_cycle(ok=False))
    await scheduler.run_monitor_cycle(state, now=1020)
    await scheduler.run_monitor_cycle(state, now=1030)
    await scheduler.run_monitor_cycle(state, now=1040)  # 3rd consecutive fail -> DOWN

    assert state.state_machine.targets["rtr01"].state == "DOWN"
    assert len(notifiers["telegram"].sent) == 1
    assert notifiers["telegram"].sent[0].new_state == "DOWN"

    monkeypatch.setattr(scheduler, "run_probe_cycle", fake_cycle(ok=True))
    await scheduler.run_monitor_cycle(state, now=1050)
    await scheduler.run_monitor_cycle(state, now=1060)  # 2nd OK -> UP, real recovery this time

    assert state.state_machine.targets["rtr01"].state == "UP"
    assert len(notifiers["telegram"].sent) == 2
    assert notifiers["telegram"].sent[1].new_state == "UP"
    assert notifiers["telegram"].sent[1].outage_duration_s == 1060 - 1040

    cursor = await conn.execute("SELECT COUNT(*) FROM state_events")
    (event_count,) = await cursor.fetchone()
    assert event_count == 4  # rtr01 UNKNOWN->UP, rtr02 UNKNOWN->UP, rtr01 UP->DOWN, rtr01 DOWN->UP

    await conn.close()


async def test_both_routers_down_sends_site_isolated_immediate_call(tmp_path, monkeypatch):
    conn = await get_db(tmp_path / "monitor.db")
    notifiers = {
        "telegram": FakeNotifier("telegram"), "whatsapp": FakeNotifier("whatsapp"),
        "ntfy": FakeNotifier("ntfy"), "telegram_call": FakeNotifier("telegram_call"),
    }
    state = make_runtime_state(conn, notifiers)

    monkeypatch.setattr(scheduler, "run_probe_cycle", fake_cycle(ok=True))
    await scheduler.run_monitor_cycle(state, now=1000)
    await scheduler.run_monitor_cycle(state, now=1010)  # both UP

    # both routers fail together, not just rtr01
    async def both_down(cfg):
        results = [
            ProbeResult(target_id="rtr01", ok=False, rtt_avg=None, rtt_min=None, rtt_max=None, loss_pct=100.0, jitter=None, method="icmp"),
            ProbeResult(target_id="rtr02", ok=False, rtt_avg=None, rtt_min=None, rtt_max=None, loss_pct=100.0, jitter=None, method="icmp"),
        ]
        return results, True

    monkeypatch.setattr(scheduler, "run_probe_cycle", both_down)
    await scheduler.run_monitor_cycle(state, now=1020)
    await scheduler.run_monitor_cycle(state, now=1030)
    await scheduler.run_monitor_cycle(state, now=1040)  # 3rd consecutive fail for both -> both DOWN

    assert state.state_machine.targets["rtr01"].state == "DOWN"
    assert state.state_machine.targets["rtr02"].state == "DOWN"
    assert state.site_isolated is True
    assert len(notifiers["telegram_call"].sent) == 1  # immediate call, no escalation wait
    assert notifiers["telegram_call"].sent[0].new_state == "SITE_ISOLATED"

    await conn.close()


async def test_muted_target_suppresses_down_and_recovery_alerts(tmp_path, monkeypatch):
    """Maintenance mode must silence notifications but keep tracking real state (CLAUDE.md/PLAN.md
    maintenance-mode rule) - a muted target that goes down should still resolve cleanly on recovery."""
    conn = await get_db(tmp_path / "monitor.db")
    notifiers = {
        "telegram": FakeNotifier("telegram"), "whatsapp": FakeNotifier("whatsapp"),
        "ntfy": FakeNotifier("ntfy"), "telegram_call": FakeNotifier("telegram_call"),
    }
    state = make_runtime_state(conn, notifiers)
    state.muted_targets["rtr01"] = 1_000_000_000  # far future - muted for this whole test

    monkeypatch.setattr(scheduler, "run_probe_cycle", fake_cycle(ok=True))
    await scheduler.run_monitor_cycle(state, now=1000)
    await scheduler.run_monitor_cycle(state, now=1010)  # both UP

    monkeypatch.setattr(scheduler, "run_probe_cycle", fake_cycle(ok=False))
    await scheduler.run_monitor_cycle(state, now=1020)
    await scheduler.run_monitor_cycle(state, now=1030)
    await scheduler.run_monitor_cycle(state, now=1040)  # rtr01 -> DOWN, but muted

    assert state.state_machine.targets["rtr01"].state == "DOWN"  # real state still tracked
    assert notifiers["telegram"].sent == []  # but nothing was sent
    assert "rtr01" in state.alert_manager.incidents  # bookkeeping kept for an accurate duration later

    monkeypatch.setattr(scheduler, "run_probe_cycle", fake_cycle(ok=True))
    await scheduler.run_monitor_cycle(state, now=1050)
    await scheduler.run_monitor_cycle(state, now=1060)  # rtr01 -> UP, still muted

    assert state.state_machine.targets["rtr01"].state == "UP"
    assert notifiers["telegram"].sent == []  # recovery also silenced
    assert "rtr01" not in state.alert_manager.incidents  # incident still resolves cleanly

    await conn.close()
