"""Asyncio probe loop. Must never die: per-target exceptions are caught and logged, cycle continues."""
from __future__ import annotations

import asyncio
import logging
import time

from app.alerts.base import Alert
from app.config import AppConfig
from app.db import insert_probe_result, insert_state_event
from app.heartbeat import send_heartbeat
from app.monitor.prober import ProbeResult, probe_canaries, probe_target
from app.monitor.state import DOWN, SITE_ISOLATED, UNKNOWN, UP, site_state

logger = logging.getLogger(__name__)


async def run_probe_cycle(cfg: AppConfig) -> tuple[list[ProbeResult], bool]:
    """Probes every target plus the canaries concurrently, once. A per-target failure logs and is skipped."""
    target_results, canary_outcome = await asyncio.gather(
        asyncio.gather(*(probe_target(t, cfg.probe) for t in cfg.targets), return_exceptions=True),
        probe_canaries(cfg.canaries, cfg.probe),
        return_exceptions=True,
    )

    results: list[ProbeResult] = []
    for target, outcome in zip(cfg.targets, target_results):
        if isinstance(outcome, Exception):
            logger.exception("probe failed for target %s", target.id, exc_info=outcome)
        else:
            results.append(outcome)

    if isinstance(canary_outcome, Exception):
        logger.exception("canary probe failed", exc_info=canary_outcome)
        canary_outcome = True  # fail open: do not freeze router alerts on our own bug

    return results, canary_outcome


async def probe_loop(cfg: AppConfig) -> None:
    """Runs run_probe_cycle every cfg.probe.interval_s, forever."""
    while True:
        results, canaries_ok = await run_probe_cycle(cfg)
        for r in results:
            logger.info(
                "%s ok=%s loss=%.0f%% rtt_avg=%s method=%s",
                r.target_id, r.ok, r.loss_pct, r.rtt_avg, r.method,
            )
        logger.info("canaries_ok=%s", canaries_ok)
        await asyncio.sleep(cfg.probe.interval_s)


async def run_monitor_cycle(state, now: float | None = None) -> None:  # state: RuntimeState (avoids import cycle)
    """One full cycle: probe -> DB write -> state machine -> alerts -> heartbeat -> broadcast."""
    now = now if now is not None else time.time()
    cfg = state.settings.app

    results, canaries_ok = await run_probe_cycle(cfg)
    state.canaries_ok = canaries_ok

    for result in results:
        state.latest_results[result.target_id] = result
        await insert_probe_result(
            state.conn, int(now), result.target_id, result.ok,
            result.rtt_avg, result.rtt_min, result.rtt_max, result.loss_pct, result.jitter, result.method,
        )

        transition = state.state_machine.evaluate(result.target_id, result.ok, now, frozen=not canaries_ok)
        if transition is None:
            continue

        await insert_state_event(
            state.conn, int(now), result.target_id, transition.from_state, transition.to_state,
            None, transition.reason,
        )

        muted = state.is_muted(result.target_id, now)

        if transition.reason == "flapping":
            if result.target_id not in state.flap_alerted:
                if not muted:
                    alert = state.build_alert(result.target_id, "FLAPPING", now)
                    await state.alert_manager._send_all(["telegram", "ntfy"], alert)
                state.flap_alerted.add(result.target_id)
            continue
        state.flap_alerted.discard(result.target_id)

        if transition.to_state == DOWN:
            await state.alert_manager.on_down(state.build_alert(result.target_id, DOWN, now), now, muted=muted)
        elif transition.to_state == UP and transition.from_state != UNKNOWN:
            # DOWN/FLAPPING -> UP is a real recovery. UNKNOWN -> UP is just startup discovery - no alert.
            incident = state.alert_manager.incidents.get(result.target_id)
            duration = int(now - incident.down_since) if incident else None
            alert = state.build_alert(result.target_id, UP, now, outage_duration_s=duration)
            await state.alert_manager.on_recovery(alert, now, muted=muted)

    # Only judge site isolation once every configured target has reported at least once -
    # a target missing from state_machine.targets must not look like a silent "all down".
    states = {t.id: state.state_machine.targets[t.id].state for t in cfg.targets if t.id in state.state_machine.targets}
    isolated = len(states) == len(cfg.targets) and site_state(states) == SITE_ISOLATED
    if isolated and not state.site_isolated:
        alert = Alert(target_id="SITE", hostname=cfg.site, ip="", new_state=SITE_ISOLATED, ts=now, severity="CRITICAL")
        await state.alert_manager.on_down(alert, now, immediate_call=True)
    elif not isolated and state.site_isolated:
        alert = Alert(target_id="SITE", hostname=cfg.site, ip="", new_state=UP, ts=now, severity="CRITICAL")
        await state.alert_manager.on_recovery(alert, now)
    state.site_isolated = isolated

    await state.alert_manager.tick(now, is_muted=lambda tid: state.is_muted(tid, now))

    if now - state.last_heartbeat_ts >= 60:
        state.last_heartbeat_ok = await send_heartbeat(state.settings.secrets.healthchecks_ping_url)
        state.last_heartbeat_ts = now

    await state.broadcast(state.status_snapshot())


async def monitor_loop(state) -> None:  # state: RuntimeState
    """Runs run_monitor_cycle every interval_s, forever. Never dies (CLAUDE.md rule 6)."""
    while True:
        try:
            await run_monitor_cycle(state)
        except Exception:
            logger.exception("monitor cycle failed - continuing")
        await asyncio.sleep(state.settings.app.probe.interval_s)
