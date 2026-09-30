"""Escalation, repeat, ACK, dedupe. Time is injected (tick(now)) so this is testable without real waits.

Escalation policy (PLAN.md section 3):
  T+0                 -> telegram + whatsapp + ntfy
  T+escalate_call_after_s, not ACKed -> telegram_call
  every repeat_every_s, not ACKed     -> telegram + telegram_call
  ACK                 -> stops repeats
  recovery            -> telegram + whatsapp
  site isolated       -> telegram_call immediately, skip the escalation wait
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.alerts.base import Alert, Notifier

logger = logging.getLogger(__name__)

SEND_TIMEOUT_S = 10
DOWN_CHANNELS = ["telegram", "whatsapp", "ntfy"]
RECOVERY_CHANNELS = ["telegram", "whatsapp"]


@dataclass
class ActiveIncident:
    alert: Alert
    down_since: float
    last_alert_ts: float
    called: bool = False
    acked: bool = False
    acked_by: str | None = None


class AlertManager:
    def __init__(self, notifiers: dict[str, Notifier], escalate_call_after_s: int, repeat_every_s: int) -> None:
        self.notifiers = notifiers
        self.escalate_call_after_s = escalate_call_after_s
        self.repeat_every_s = repeat_every_s
        self.incidents: dict[str, ActiveIncident] = {}

    async def on_down(self, alert: Alert, now: float, immediate_call: bool = False, muted: bool = False) -> None:
        """muted=True still tracks the incident (for an accurate recovery duration later) but
        sends nothing - maintenance mode suppresses notifications, not internal bookkeeping."""
        incident = ActiveIncident(alert=alert, down_since=now, last_alert_ts=now)
        self.incidents[alert.target_id] = incident
        if muted:
            return
        await self._send_all(DOWN_CHANNELS, alert)
        if immediate_call:
            await self._send("telegram_call", alert)
            incident.called = True

    async def on_recovery(self, alert: Alert, now: float, muted: bool = False) -> None:
        self.incidents.pop(alert.target_id, None)
        if muted:
            return
        await self._send_all(RECOVERY_CHANNELS, alert)

    async def tick(self, now: float, is_muted: Callable[[str], bool] | None = None) -> None:
        """Call periodically (e.g. once per probe cycle) to drive escalation and repeats.

        is_muted lets a currently-muted incident keep existing (so it still resolves normally on
        recovery) without escalating or repeating while muted.
        """
        is_muted = is_muted or (lambda _target_id: False)
        for incident in list(self.incidents.values()):
            if incident.acked or is_muted(incident.alert.target_id):
                continue
            if not incident.called and now - incident.down_since >= self.escalate_call_after_s:
                await self._send("telegram_call", incident.alert)
                incident.called = True
                incident.last_alert_ts = now
            elif now - incident.last_alert_ts >= self.repeat_every_s:
                await self._send_all(["telegram", "telegram_call"], incident.alert)
                incident.last_alert_ts = now

    def ack(self, target_id: str, by: str) -> bool:
        incident = self.incidents.get(target_id)
        if incident is None:
            return False
        incident.acked = True
        incident.acked_by = by
        return True

    async def _send(self, channel: str, alert: Alert) -> bool:
        notifier = self.notifiers.get(channel)
        if notifier is None:
            return False
        try:
            return await asyncio.wait_for(notifier.send(alert), timeout=SEND_TIMEOUT_S)
        except Exception:
            logger.exception("notifier %s failed to send for %s", channel, alert.target_id)
            return False

    async def _send_all(self, channels: list[str], alert: Alert) -> None:
        await asyncio.gather(*(self._send(ch, alert) for ch in channels))
