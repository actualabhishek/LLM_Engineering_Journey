"""CallMeBot: free Telegram voice call (the "loud" escalation layer) and WhatsApp text.

Free, personal-use, third-party service with no SLA and no official client - plain HTTP GET.
Endpoints verified at build time (2026-09) against callmebot.com/telegram-call-api and
callmebot.com/blog/free-api-whatsapp-messages. One-time authorisation required per channel:
  - Telegram call: visit https://api2.callmebot.com/txt/login.php, or send /start to @CallMeBot_txtbot
  - WhatsApp: message "I allow callmebot to send me messages" to +34 611 021 695 on WhatsApp
"""
from __future__ import annotations

import logging

import httpx

from app.alerts.base import Alert, Notifier
from app.alerts.format import format_message

logger = logging.getLogger(__name__)
TIMEOUT_S = 15  # CallMeBot can be slow; still bounded so it never blocks the probe loop


def _body_says_error(body: str) -> str | None:
    """CallMeBot returns HTTP 200 even on failure (rate limit, not authorised, etc) - the real
    result is a line starting with "ERROR" in the HTML body. Returns that line, or None if ok."""
    for line in body.splitlines():
        if line.strip().upper().startswith("ERROR"):
            return line.strip()
    return None


class CallMeBotCallNotifier(Notifier):
    """Places a real Telegram voice call and reads the alert text via TTS."""

    name = "telegram_call"

    def __init__(self, tg_user: str) -> None:
        self.tg_user = tg_user

    async def send(self, alert: Alert) -> bool:
        if not self.tg_user:
            logger.warning("callmebot call not configured, skipping alert for %s", alert.target_id)
            return False

        text = format_message(alert).replace("\n", ". ")[:256]
        params = {"user": self.tg_user, "text": text, "lang": "en-GB-Standard-B", "rpt": "2"}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                resp = await client.get("http://api.callmebot.com/start.php", params=params)
                resp.raise_for_status()
            error = _body_says_error(resp.text)
            if error:
                logger.warning("callmebot call rejected for %s: %s", alert.target_id, error)
                return False
            return True
        except httpx.HTTPError:
            logger.exception("callmebot call failed for %s", alert.target_id)
            return False


class CallMeBotWhatsAppNotifier(Notifier):
    """WhatsApp text via CallMeBot. Best-effort, rate limited."""

    name = "whatsapp"

    def __init__(self, phone: str, apikey: str) -> None:
        self.phone = phone
        self.apikey = apikey

    async def send(self, alert: Alert) -> bool:
        if not self.phone or not self.apikey:
            logger.warning("callmebot whatsapp not configured, skipping alert for %s", alert.target_id)
            return False

        params = {"phone": self.phone, "text": format_message(alert), "apikey": self.apikey}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                resp = await client.get("https://api.callmebot.com/whatsapp.php", params=params)
                resp.raise_for_status()
            error = _body_says_error(resp.text)
            if error:
                logger.warning("callmebot whatsapp rejected for %s: %s", alert.target_id, error)
                return False
            return True
        except httpx.HTTPError:
            logger.exception("callmebot whatsapp failed for %s", alert.target_id)
            return False
