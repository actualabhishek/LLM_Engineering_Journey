"""SQLite schema and access. All timestamps stored as UTC epoch seconds."""
from __future__ import annotations

from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (
    id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    ip TEXT NOT NULL,
    tcp_port INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS probe_results (
    ts INTEGER NOT NULL,
    target_id TEXT NOT NULL,
    ok INTEGER NOT NULL,
    rtt_avg REAL,
    rtt_min REAL,
    rtt_max REAL,
    loss_pct REAL,
    jitter REAL,
    method TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_probe_results_target_ts ON probe_results (target_id, ts);

CREATE TABLE IF NOT EXISTS state_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    target_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    duration_s INTEGER,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    event_id INTEGER,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    acked_by TEXT,
    acked_ts INTEGER,
    error TEXT
);

CREATE TABLE IF NOT EXISTS maintenance (
    target_id TEXT NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS probe_results_rollup (
    ts_bucket INTEGER NOT NULL,
    target_id TEXT NOT NULL,
    ok_pct REAL NOT NULL,
    rtt_avg REAL,
    loss_avg REAL
);
CREATE INDEX IF NOT EXISTS idx_rollup_target_ts ON probe_results_rollup (target_id, ts_bucket);
"""

ROLLUP_BUCKET_S = 300  # 5 minutes


async def get_db(db_path: Path) -> aiosqlite.Connection:
    """Opens the SQLite connection and creates the schema if it does not exist yet."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    await conn.executescript(SCHEMA)
    await conn.commit()
    return conn


async def insert_probe_result(
    conn: aiosqlite.Connection,
    ts: int,
    target_id: str,
    ok: bool,
    rtt_avg: float | None,
    rtt_min: float | None,
    rtt_max: float | None,
    loss_pct: float,
    jitter: float | None,
    method: str,
) -> None:
    await conn.execute(
        "INSERT INTO probe_results (ts, target_id, ok, rtt_avg, rtt_min, rtt_max, loss_pct, jitter, method) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, target_id, int(ok), rtt_avg, rtt_min, rtt_max, loss_pct, jitter, method),
    )
    await conn.commit()


async def insert_state_event(
    conn: aiosqlite.Connection,
    ts: int,
    target_id: str,
    from_state: str,
    to_state: str,
    duration_s: int | None,
    reason: str | None,
) -> int:
    cursor = await conn.execute(
        "INSERT INTO state_events (ts, target_id, from_state, to_state, duration_s, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ts, target_id, from_state, to_state, duration_s, reason),
    )
    await conn.commit()
    return cursor.lastrowid


async def insert_alert(
    conn: aiosqlite.Connection, ts: int, event_id: int | None, channel: str, status: str, error: str | None = None
) -> int:
    cursor = await conn.execute(
        "INSERT INTO alerts (ts, event_id, channel, status, error) VALUES (?, ?, ?, ?, ?)",
        (ts, event_id, channel, status, error),
    )
    await conn.commit()
    return cursor.lastrowid


async def get_latest_status(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    """Latest probe_results row per target_id."""
    conn.row_factory = aiosqlite.Row
    cursor = await conn.execute(
        "SELECT p.* FROM probe_results p "
        "JOIN (SELECT target_id, MAX(ts) AS max_ts FROM probe_results GROUP BY target_id) latest "
        "ON p.target_id = latest.target_id AND p.ts = latest.max_ts"
    )
    return await cursor.fetchall()


async def get_history(conn: aiosqlite.Connection, target_id: str, since_ts: int) -> list[aiosqlite.Row]:
    conn.row_factory = aiosqlite.Row
    cursor = await conn.execute(
        "SELECT * FROM probe_results WHERE target_id = ? AND ts >= ? ORDER BY ts", (target_id, since_ts)
    )
    return await cursor.fetchall()


async def get_events(conn: aiosqlite.Connection, limit: int = 100) -> list[aiosqlite.Row]:
    conn.row_factory = aiosqlite.Row
    cursor = await conn.execute("SELECT * FROM state_events ORDER BY ts DESC LIMIT ?", (limit,))
    return await cursor.fetchall()


async def run_retention(conn: aiosqlite.Connection, now: int, raw_retention_days: int = 30) -> int:
    """Rolls up probe_results older than raw_retention_days into 5-min buckets, then deletes the raw rows.

    Returns the number of raw rows deleted.
    """
    cutoff = now - raw_retention_days * 86400

    await conn.execute(
        "INSERT INTO probe_results_rollup (ts_bucket, target_id, ok_pct, rtt_avg, loss_avg) "
        "SELECT (ts / ?) * ?, target_id, AVG(ok) * 100, AVG(rtt_avg), AVG(loss_pct) "
        "FROM probe_results WHERE ts < ? GROUP BY target_id, ts / ?",
        (ROLLUP_BUCKET_S, ROLLUP_BUCKET_S, cutoff, ROLLUP_BUCKET_S),
    )
    cursor = await conn.execute("DELETE FROM probe_results WHERE ts < ?", (cutoff,))
    await conn.commit()
    return cursor.rowcount
