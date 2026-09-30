"""Shared runtime state: DB connection, state machine, alert manager, latest results, websocket clients.

One instance lives on app.state for the life of the process (see app/main.py lifespan).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import aiosqlite
from fastapi import WebSocket

from app.alerts.base import Alert
from app.alerts.manager import AlertManager
from app.config import Settings
from app.monitor.prober import ProbeResult
from app.monitor.state import DOWN, SITE_ISOLATED, StateMachine, site_state

logger = logging.getLogger(__name__)


@dataclass
class RuntimeState:
    settings: Settings
    conn: aiosqlite.Connection
    state_machine: StateMachine
    alert_manager: AlertManager
    started_at: float = field(default_factory=time.time)
    latest_results: dict[str, ProbeResult] = field(default_factory=dict)
    canaries_ok: bool = True
    last_heartbeat_ok: bool | None = None
    websockets: set[WebSocket] = field(default_factory=set)
    muted_targets: dict[str, float] = field(default_factory=dict)  # target_id -> mute-until epoch
    site_isolated: bool = False
    flap_alerted: set[str] = field(default_factory=set)  # targets already notified for the current flap episode
    last_heartbeat_ts: float = 0

    def is_muted(self, target_id: str, now: float) -> bool:
        until = self.muted_targets.get(target_id)
        return until is not None and now < until

    def target_by_id(self, target_id: str):
        for t in self.settings.app.targets:
            if t.id == target_id:
                return t
        return None

    def build_alert(self, target_id: str, new_state: str, now: float, outage_duration_s: int | None = None) -> Alert:
        target = self.target_by_id(target_id)
        result = self.latest_results.get(target_id)
        severity = "CRITICAL" if new_state in (DOWN, SITE_ISOLATED) else "WARNING"
        return Alert(
            target_id=target_id,
            hostname=target.hostname if target else target_id,
            ip=target.ip if target else "",
            new_state=new_state,
            ts=now,
            severity=severity,
            rtt_avg=result.rtt_avg if result else None,
            loss_pct=result.loss_pct if result else None,
            outage_duration_s=outage_duration_s,
        )

    def status_snapshot(self) -> dict:
        now = time.time()
        targets = []
        for t in self.settings.app.targets:
            result = self.latest_results.get(t.id)
            ts = self.state_machine.targets.get(t.id)
            targets.append(
                {
                    "id": t.id,
                    "hostname": t.hostname,
                    "ip": t.ip,
                    "state": ts.state if ts else "UNKNOWN",
                    "ok": result.ok if result else None,
                    "rtt_avg": result.rtt_avg if result else None,
                    "loss_pct": result.loss_pct if result else None,
                    "last_change_ts": ts.last_change_ts if ts else None,
                    "muted": self.is_muted(t.id, now),
                    "muted_until": self.muted_targets.get(t.id) if self.is_muted(t.id, now) else None,
                }
            )
        return {
            "site": self.settings.app.site,
            "site_state": SITE_ISOLATED if self.site_isolated else "OK",
            "canaries_ok": self.canaries_ok,
            "last_heartbeat_ok": self.last_heartbeat_ok,
            "targets": targets,
            "ts": now,
        }

    async def broadcast(self, payload: dict) -> None:
        dead = set()
        for ws in self.websockets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.add(ws)
        self.websockets -= dead
