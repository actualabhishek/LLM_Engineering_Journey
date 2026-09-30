"""Notifier interface. Each channel implements send(); channels are independent (CLAUDE.md rule 5)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Alert:
    target_id: str
    hostname: str
    ip: str
    new_state: str  # UP, DOWN, FLAPPING, SITE_ISOLATED, MONITOR_ISOLATED
    ts: float  # epoch seconds UTC
    severity: str = "WARNING"  # WARNING or CRITICAL
    rtt_avg: float | None = None
    loss_pct: float | None = None
    outage_duration_s: int | None = None  # set on recovery alerts


class Notifier(ABC):
    """One notifier per alert channel. send() must not raise - callers wrap it anyway, but
    implementations should catch their own request errors and return False."""

    name: str

    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        ...
