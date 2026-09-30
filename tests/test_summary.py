"""Tests for the daily/on-demand summary builder against a real temp SQLite DB."""
import pytest

from app.db import get_db, insert_probe_result, insert_state_event
from app.alerts.summary import build_summary

pytestmark = pytest.mark.asyncio


async def test_summary_computes_uptime_outages_rtt_loss(tmp_path):
    conn = await get_db(tmp_path / "monitor.db")
    since = 1_700_000_000
    now = since + 3600  # 1h window

    # rtr01: 4 ok, 1 fail (80% uptime), one DOWN event, avg rtt from the ok rows only
    await insert_probe_result(conn, since + 0, "rtr01", True, 300.0, 290.0, 310.0, 0.0, 1.0, "icmp")
    await insert_probe_result(conn, since + 10, "rtr01", True, 320.0, 310.0, 330.0, 0.0, 1.0, "icmp")
    await insert_probe_result(conn, since + 20, "rtr01", False, None, None, None, 100.0, None, "icmp")
    await insert_probe_result(conn, since + 30, "rtr01", True, 310.0, 300.0, 320.0, 0.0, 1.0, "icmp")
    await insert_probe_result(conn, since + 40, "rtr01", True, 300.0, 290.0, 310.0, 0.0, 1.0, "icmp")
    await insert_state_event(conn, since + 20, "rtr01", "UP", "DOWN", None, "debounce")

    # rtr02: always ok, 100% uptime, no outages
    for i in range(5):
        await insert_probe_result(conn, since + i * 10, "rtr02", True, 315.0, 305.0, 325.0, 0.0, 1.0, "icmp")

    summary = await build_summary(conn, ["rtr01", "rtr02", "rtr03"], since, now)

    assert "Summary - last 1h" in summary
    assert "rtr01: uptime=80.0% outages=1 avg_rtt=" in summary
    assert "max_loss=100%" in summary
    assert "rtr02: uptime=100.0% outages=0" in summary
    assert "rtr03: no data" in summary

    await conn.close()
