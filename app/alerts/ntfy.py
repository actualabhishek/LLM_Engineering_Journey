"""ntfy.sh: free push notifications. Priority 5 bypasses Do Not Disturb - good backup if CallMeBot is slow."""
from __future__ import annotations

import logging

import httpx

from app.alerts.base import Alert, Notifier
from app.alerts.format import format_message

logger = logging.getLogger(__name__)
TIMEOUT_S = 10


class NtfyNotifier(Notifier):
    name = "ntfy"

    def __init__(self, topic: str) -> None:
        self.topic = topic

    async def send(self, alert: Alert) -> bool:
        if not self.topic:
            logger.warning("ntfy not configured, skipping alert for %s", alert.target_id)
            return False

        priority = "5" if alert.severity == "CRITICAL" else "4"
        headers = {
            "Title": f"{alert.hostname} is {alert.new_state}".encode("ascii", "ignore"),
            "Priority": priority,
            "Tags": "rotating_light" if alert.new_state != "UP" else "white_check_mark",
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                resp = await client.post(
                    f"https://ntfy.sh/{self.topic}", data=format_message(alert).encode("utf-8"), headers=headers
                )
                resp.raise_for_status()
            return True
        except httpx.HTTPError:
            logger.exception("ntfy send failed for %s", alert.target_id)
            return False
