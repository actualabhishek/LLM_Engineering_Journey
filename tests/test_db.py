"""SQLite storage tests: schema creation, writes, queries, retention rollup."""
import pytest

from app.db import (
    get_db,
    get_events,
    get_history,
    get_latest_status,
    insert_alert,
    insert_probe_result,
    insert_state_event,
    run_retention,
)

pytestmark = pytest.mark.asyncio


async def test_schema_creates_on_empty_db(tmp_path):
    conn = await get_db(tmp_path / "monitor.db")
    cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in await cursor.fetchall()}
    await conn.close()
    assert {"targets", "probe_results", "state_events", "alerts", "maintenance", "probe_results_rollup"} <= tables


async def test_insert_and_query_round_trip(tmp_path):
    conn = await get_db(tmp_path / "monitor.db")
    now = 1_700_000_000

    await insert_probe_result(conn, now, "rtr01", True, 320.1, 310.0, 330.0, 0.0, 3.2, "icmp")
    await insert_probe_result(conn, now + 10, "rtr01", False, None, None, None, 100.0, None, "icmp")
    await insert_probe_result(conn, now + 10, "rtr02", True, 315.0, 300.0, 320.0, 0.0, 1.1, "icmp")

    event_id = await insert_state_event(conn, now + 10, "rtr01", "UP", "DOWN", None, "debounce")
    await insert_alert(conn, now + 10, event_id, "telegram", "sent")

    latest = await get_latest_status(conn)
    latest_by_target = {row["target_id"]: row for row in latest}
    assert latest_by_target["rtr01"]["ok"] == 0
    assert latest_by_target["rtr02"]["ok"] == 1

    history = await get_history(conn, "rtr01", now)
    assert [row["ts"] for row in history] == [now, now + 10]

    events = await get_events(conn)
    assert len(events) == 1
    assert events[0]["from_state"] == "UP"
    assert events[0]["to_state"] == "DOWN"

    await conn.close()


async def test_retention_rolls_up_and_deletes_old_rows(tmp_path):
    conn = await get_db(tmp_path / "monitor.db")
    now = 1_700_000_000
    old_ts = now - 40 * 86400  # older than the 30-day default retention

    await insert_probe_result(conn, now, "rtr01", True, 320.0, 310.0, 330.0, 0.0, 1.0, "icmp")
    await insert_probe_result(conn, old_ts, "rtr01", True, 300.0, 290.0, 310.0, 0.0, 1.0, "icmp")

    deleted = await run_retention(conn, now=now, raw_retention_days=30)
    assert deleted == 1

    cursor = await conn.execute("SELECT COUNT(*) FROM probe_results")
    (remaining,) = await cursor.fetchone()
    assert remaining == 1  # only the recent row is left

    cursor = await conn.execute("SELECT COUNT(*) FROM probe_results_rollup WHERE target_id = 'rtr01'")
    (rollup_rows,) = await cursor.fetchone()
    assert rollup_rows == 1

    await conn.close()
