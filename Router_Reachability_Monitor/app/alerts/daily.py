"""Daily summary at 09:00 IST: uptime %, outages, avg RTT, max loss for the last 24h."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.alerts.summary import build_summary
from app.alerts.telegram import send_text
from app.runtime import RuntimeState

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
SUMMARY_HOUR_IST = 9


def seconds_until_next_run(now: datetime) -> float:
    """Pure: given the current IST time, how long until the next 09:00 IST."""
    next_run = now.replace(hour=SUMMARY_HOUR_IST, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return (next_run - now).total_seconds()


async def daily_summary_loop(state: RuntimeState) -> None:
    """Sleeps until the next 09:00 IST, sends the summary, repeats. Never dies (CLAUDE.md rule 6)."""
    while True:
        sleep_s = seconds_until_next_run(datetime.now(IST))
        await asyncio.sleep(sleep_s)
        try:
            target_ids = [t.id for t in state.settings.app.targets]
            now = time.time()
            summary = await build_summary(state.conn, target_ids, int(now - 86400), int(now))
            secrets = state.settings.secrets
            await send_text(secrets.telegram_bot_token, secrets.telegram_chat_id, summary)
        except Exception:
            logger.exception("daily summary failed - will retry tomorrow")
