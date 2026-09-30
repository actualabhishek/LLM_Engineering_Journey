"""Tests for the pure Telegram command handler - no real Telegram network calls."""
import pytest

from app.alerts.base import Alert
from app.alerts.manager import AlertManager
from app.alerts.telegram_bot import HELP_TEXT, _handle_callback, handle_command
from app.config import AppConfig, FlapConfig, ProbeConfig, Secrets, Settings, Target
from app.db import get_db
from app.monitor.state import StateMachine
from app.runtime import RuntimeState

pytestmark = pytest.mark.asyncio


class FakeClient:
    """Records every .post() call instead of hitting the real Telegram API."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url, json):
        self.calls.append((url, json))


async def make_state(tmp_path):
    conn = await get_db(tmp_path / "monitor.db")
    app_cfg = AppConfig(
        site="LI-MDF",
        probe=ProbeConfig(),
        flap=FlapConfig(),
        targets=[
            Target(id="rtr01", hostname="RTR01", ip="203.0.113.1", tcp_port=22),
            Target(id="rtr02", hostname="RTR02", ip="203.0.113.2", tcp_port=22),
        ],
    )
    settings = Settings(app=app_cfg, secrets=Secrets())
    sm = StateMachine(3, 2, 4, 600)
    am = AlertManager({}, escalate_call_after_s=120, repeat_every_s=600)
    return RuntimeState(settings=settings, conn=conn, state_machine=sm, alert_manager=am)


async def test_help_and_start():
    state = None  # these commands never touch state
    assert await handle_command(state, "/help") == HELP_TEXT
    assert await handle_command(state, "/start") == HELP_TEXT


async def test_status_reports_target_states(tmp_path):
    state = await make_state(tmp_path)
    state.state_machine.evaluate("rtr01", ok=True, now=0)
    state.state_machine.evaluate("rtr01", ok=True, now=10)  # UP

    reply = await handle_command(state, "/status")
    assert "LI-MDF" in reply
    assert "RTR01: UP" in reply
    assert "RTR02: UNKNOWN" in reply
    await state.conn.close()


async def test_mute_and_unmute(tmp_path):
    state = await make_state(tmp_path)

    reply = await handle_command(state, "/mute rtr01 30")
    assert reply == "rtr01 muted for 30m"
    assert "rtr01" in state.muted_targets

    reply = await handle_command(state, "/mute unknown-target")
    assert "Unknown target" in reply

    reply = await handle_command(state, "/unmute rtr01")
    assert reply == "rtr01 unmuted"
    assert "rtr01" not in state.muted_targets

    reply = await handle_command(state, "/unmute rtr01")
    assert "was not muted" in reply
    await state.conn.close()


async def test_ack_with_and_without_incident(tmp_path):
    state = await make_state(tmp_path)

    reply = await handle_command(state, "/ack rtr01")
    assert "No active incident" in reply

    alert = Alert(target_id="rtr01", hostname="RTR01", ip="203.0.113.1", new_state="DOWN", ts=1000)
    await state.alert_manager.on_down(alert, now=1000)

    reply = await handle_command(state, "/ack rtr01")
    assert reply == "Acked rtr01"
    assert state.alert_manager.incidents["rtr01"].acked is True
    assert state.alert_manager.incidents["rtr01"].acked_by == "telegram"
    await state.conn.close()


async def test_report_returns_summary_text(tmp_path):
    state = await make_state(tmp_path)
    reply = await handle_command(state, "/report")
    assert reply.startswith("Summary - last")
    await state.conn.close()


async def test_unknown_command_returns_none(tmp_path):
    state = await make_state(tmp_path)
    assert await handle_command(state, "/bogus") is None
    assert await handle_command(state, "") is None
    await state.conn.close()


async def test_ack_button_edits_the_message_for_everyone(tmp_path):
    """Pressing ACK must visibly change the message itself (not just a private toast), so
    everyone in a shared channel sees it was handled and can't double-press the button."""
    state = await make_state(tmp_path)
    alert = Alert(target_id="rtr01", hostname="RTR01", ip="203.0.113.1", new_state="DOWN", ts=1000)
    await state.alert_manager.on_down(alert, now=1000)

    client = FakeClient()
    callback = {
        "id": "cbq1",
        "data": "ack:rtr01",
        "from": {"username": "netops_alice"},
        "message": {"chat": {"id": -1001}, "message_id": 55, "text": "[WARNING] RTR01 is DOWN"},
    }
    await _handle_callback(state, client, "token", callback)

    assert state.alert_manager.incidents["rtr01"].acked is True
    edit_calls = [c for c in client.calls if c[0].endswith("/editMessageText")]
    assert len(edit_calls) == 1
    _, payload = edit_calls[0]
    assert payload["chat_id"] == -1001
    assert payload["message_id"] == 55
    assert "Acknowledged by netops_alice" in payload["text"]
    assert payload["text"].startswith("[WARNING] RTR01 is DOWN")
    assert payload["reply_markup"] == {"inline_keyboard": []}

    answer_calls = [c for c in client.calls if c[0].endswith("/answerCallbackQuery")]
    assert len(answer_calls) == 1
    assert answer_calls[0][1]["callback_query_id"] == "cbq1"
    await state.conn.close()


async def test_ack_button_no_active_incident_does_not_edit_message(tmp_path):
    """Stale button on an already-resolved incident: acknowledge the tap, but don't touch the
    (now-irrelevant) message text."""
    state = await make_state(tmp_path)

    client = FakeClient()
    callback = {
        "id": "cbq2",
        "data": "ack:rtr01",
        "from": {"username": "netops_bob"},
        "message": {"chat": {"id": -1001}, "message_id": 56, "text": "[WARNING] RTR01 is DOWN"},
    }
    await _handle_callback(state, client, "token", callback)

    edit_calls = [c for c in client.calls if c[0].endswith("/editMessageText")]
    assert edit_calls == []
    answer_calls = [c for c in client.calls if c[0].endswith("/answerCallbackQuery")]
    assert "No active incident" in answer_calls[0][1]["text"]
    await state.conn.close()
