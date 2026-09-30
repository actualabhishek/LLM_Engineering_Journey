"""Uptime %, outage count, avg RTT, max loss over a period - used by /report and the daily summary."""
from __future__ import annotations

import aiosqlite


async def build_summary(conn: aiosqlite.Connection, target_ids: list[str], since_ts: int, now_ts: int) -> str:
    hours = max(1, (now_ts - since_ts) // 3600)
    lines = [f"Summary - last {hours}h"]

    for target_id in target_ids:
        cursor = await conn.execute(
            "SELECT COUNT(*), SUM(ok), AVG(rtt_avg), MAX(loss_pct) FROM probe_results WHERE target_id = ? AND ts >= ?",
            (target_id, since_ts),
        )
        total, ok_count, avg_rtt, max_loss = await cursor.fetchone()

        if not total:
            lines.append(f"{target_id}: no data")
            continue

        cursor = await conn.execute(
            "SELECT COUNT(*) FROM state_events WHERE target_id = ? AND to_state = 'DOWN' AND ts >= ?",
            (target_id, since_ts),
        )
        (outages,) = await cursor.fetchone()

        uptime_pct = (ok_count or 0) / total * 100
        rtt_str = f"{avg_rtt:.0f}ms" if avg_rtt is not None else "n/a"
        loss_str = f"{max_loss:.0f}%" if max_loss is not None else "n/a"
        lines.append(f"{target_id}: uptime={uptime_pct:.1f}% outages={outages} avg_rtt={rtt_str} max_loss={loss_str}")

    return "\n".join(lines)
