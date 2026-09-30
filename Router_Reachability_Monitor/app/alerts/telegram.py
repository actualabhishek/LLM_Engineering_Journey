"""Telegram Bot API: text alerts with an inline ACK button. Primary channel - reliable, free, unlimited."""
from __future__ import annotations

import logging

import httpx

from app.alerts.base import Alert, Notifier
from app.alerts.format import format_message

logger = logging.getLogger(__name__)
API_BASE = "https://api.telegram.org"
TIMEOUT_S = 10


async def send_text(bot_token: str, chat_id: str, text: str, reply_markup: dict | None = None) -> bool:
    """Raw sendMessage call, reused by the DOWN/recovery notifier, the bot's command replies, and
    the daily summary - none of those are a state-change Alert, so they bypass TelegramNotifier."""
    if not bot_token or not chat_id:
        return False

    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            resp = await client.post(f"{API_BASE}/bot{bot_token}/sendMessage", json=payload)
            resp.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("telegram send_text failed")
        return False


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, alert: Alert) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.warning("telegram not configured, skipping alert for %s", alert.target_id)
            return False

        reply_markup = None
        if alert.new_state == "DOWN":
            reply_markup = {"inline_keyboard": [[{"text": "ACK", "callback_data": f"ack:{alert.target_id}"}]]}

        return await send_text(self.bot_token, self.chat_id, format_message(alert), reply_markup)
