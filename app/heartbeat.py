"""Dead-man's switch: ping healthchecks.io every cycle. If this stops, healthchecks.io alerts the owner."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)
TIMEOUT_S = 10


async def send_heartbeat(ping_url: str) -> bool:
    if not ping_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            resp = await client.get(ping_url)
            resp.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("heartbeat ping failed")
        return False
