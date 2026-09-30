"""ICMP + TCP probes. Pure I/O, no state-machine logic here (see state.py)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from icmplib import async_ping
from icmplib.exceptions import SocketPermissionError

from app.config import ProbeConfig, Target

logger = logging.getLogger(__name__)

# Privileged (raw socket) ICMP is what the container's NET_RAW capability is for; it also works
# unprivileged on Windows dev and on Linux hosts with a permissive ping_group_range. Whichever
# mode actually works is detected once per process and reused, instead of failing every cycle.
_use_privileged: bool | None = None


@dataclass
class ProbeResult:
    target_id: str
    ok: bool
    rtt_avg: float | None
    rtt_min: float | None
    rtt_max: float | None
    loss_pct: float
    jitter: float | None
    method: str  # "icmp" or "tcp"


async def icmp_probe(ip: str, count: int, timeout: float) -> ProbeResult:
    """Sends `count` ICMP echoes. Returns loss/RTT/jitter. ok = at least one reply.

    Tries privileged (raw socket) mode first - what NET_RAW is granted for in Docker. Falls back
    to unprivileged mode if that's not permitted (e.g. Windows dev without admin), and remembers
    the outcome so we don't retry the failing mode on every single cycle.
    """
    global _use_privileged
    if _use_privileged is None:
        try:
            host = await async_ping(ip, count=count, timeout=timeout, privileged=True)
            _use_privileged = True
        except SocketPermissionError:
            logger.info("privileged ICMP not permitted, falling back to unprivileged mode")
            _use_privileged = False
            host = await async_ping(ip, count=count, timeout=timeout, privileged=False)
    else:
        host = await async_ping(ip, count=count, timeout=timeout, privileged=_use_privileged)
    return ProbeResult(
        target_id="",
        ok=host.is_alive,
        rtt_avg=host.avg_rtt if host.is_alive else None,
        rtt_min=host.min_rtt if host.is_alive else None,
        rtt_max=host.max_rtt if host.is_alive else None,
        loss_pct=host.packet_loss * 100,
        jitter=host.jitter if host.is_alive else None,
        method="icmp",
    )


async def tcp_probe(ip: str, port: int, timeout: float) -> bool:
    """TCP connect probe, used as a fallback when ICMP is dropped (e.g. CoPP)."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


async def probe_target(target: Target, cfg: ProbeConfig) -> ProbeResult:
    """Probes one target: ICMP first, TCP fallback only if ICMP fully failed and enabled."""
    result = await icmp_probe(target.ip, cfg.icmp_count, cfg.icmp_timeout_s)
    result.target_id = target.id

    if not result.ok and cfg.tcp_fallback:
        tcp_ok = await tcp_probe(target.ip, target.tcp_port, cfg.icmp_timeout_s)
        if tcp_ok:
            result.ok = True
            result.method = "tcp"

    return result


async def probe_canaries(canaries: list[str], cfg: ProbeConfig) -> bool:
    """Returns True if at least one canary (e.g. 1.1.1.1) replies. All failing means our own internet is down."""
    results = await asyncio.gather(
        *(icmp_probe(ip, cfg.icmp_count, cfg.icmp_timeout_s) for ip in canaries)
    )
    return any(r.ok for r in results)
