"""Telegram bot commands: /status /mute /unmute /ack /report, plus the inline ACK button callback.

Uses long-polling (getUpdates) rather than a webhook - no public HTTPS endpoint needed, so this
works even before Tailscale Funnel is set up (Phase 8).
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.alerts.summary import build_summary
from app.alerts.telegram import send_text
from app.runtime import RuntimeState

logger = logging.getLogger(__name__)
API_BASE = "https://api.telegram.org"
POLL_TIMEOUT_S = 30
HELP_TEXT = "Commands: /status /mute <id> [minutes] /unmute <id> /ack <id> /report"


async def handle_command(state: RuntimeState, text: str) -> str | None:
    """Pure-ish: only touches RuntimeState, no network. Testable without a real Telegram client."""
    parts = text.strip().split()
    if not parts:
        return None
    cmd = parts[0].lower().split("@")[0]  # strip a "/status@botname" suffix

    if cmd == "/start" or cmd == "/help":
        return HELP_TEXT

    if cmd == "/status":
        return _format_status(state)

    if cmd == "/mute" and len(parts) >= 2:
        target_id = parts[1]
        if state.target_by_id(target_id) is None:
            return f"Unknown target {target_id}"
        minutes = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 60
        state.muted_targets[target_id] = time.time() + minutes * 60
        return f"{target_id} muted for {minutes}m"

    if cmd == "/unmute" and len(parts) >= 2:
        target_id = parts[1]
        was_muted = state.muted_targets.pop(target_id, None) is not None
        return f"{target_id} unmuted" if was_muted else f"{target_id} was not muted"

    if cmd == "/ack" and len(parts) >= 2:
        target_id = parts[1]
        acked = state.alert_manager.ack(target_id, by="telegram")
        return f"Acked {target_id}" if acked else f"No active incident for {target_id}"

    if cmd == "/report":
        target_ids = [t.id for t in state.settings.app.targets]
        now = time.time()
        return await build_summary(state.conn, target_ids, int(now - 86400), int(now))

    return None


def _format_status(state: RuntimeState) -> str:
    snap = state.status_snapshot()
    lines = [f"{snap['site']} - {snap['site_state']}"]
    for t in snap["targets"]:
        muted = " (muted)" if t["muted"] else ""
        rtt = f"{t['rtt_avg']:.0f}ms" if t["rtt_avg"] is not None else "n/a"
        lines.append(f"{t['hostname']}: {t['state']}{muted} rtt={rtt} loss={t['loss_pct']}%")
    return "\n".join(lines)


async def _handle_callback(state: RuntimeState, client: httpx.AsyncClient, token: str, callback: dict) -> None:
    data = callback.get("data", "")
    text = "Unknown action"
    if data.startswith("ack:"):
        target_id = data[len("ack:") :]
        by = callback.get("from", {}).get("username") or "telegram"
        acked = state.alert_manager.ack(target_id, by=by)
        text = f"Acked {target_id}" if acked else f"No active incident for {target_id}"

    try:
        await client.post(
            f"{API_BASE}/bot{token}/answerCallbackQuery",
            json={"callback_query_id": callback["id"], "text": text},
        )
    except httpx.HTTPError:
        logger.exception("answerCallbackQuery failed")


async def _handle_update(state: RuntimeState, client: httpx.AsyncClient, token: str, update: dict) -> None:
    if "callback_query" in update:
        await _handle_callback(state, client, token, update["callback_query"])
        return

    message = update.get("message")
    if not message or "text" not in message:
        return

    chat_id = str(message["chat"]["id"])
    reply = await handle_command(state, message["text"])
    if reply:
        await send_text(token, chat_id, reply)


async def telegram_bot_loop(state: RuntimeState) -> None:
    """Long-polls Telegram for commands, forever. Never dies (CLAUDE.md rule 6)."""
    token = state.settings.secrets.telegram_bot_token
    if not token:
        logger.info("telegram bot token not set, bot commands disabled")
        return

    offset = 0
    async with httpx.AsyncClient(timeout=POLL_TIMEOUT_S + 10) as client:
        while True:
            try:
                resp = await client.get(
                    f"{API_BASE}/bot{token}/getUpdates", params={"offset": offset, "timeout": POLL_TIMEOUT_S}
                )
                resp.raise_for_status()
                for update in resp.json().get("result", []):
                    offset = update["update_id"] + 1
                    await _handle_update(state, client, token, update)
            except Exception:
                logger.exception("telegram bot poll failed - retrying in 5s")
                await asyncio.sleep(5)
