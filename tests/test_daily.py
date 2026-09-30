"""Tests for the daily summary's next-run calculation (pure, no real sleeping)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.alerts.daily import seconds_until_next_run

IST = ZoneInfo("Asia/Kolkata")


def test_before_9am_waits_until_9am_today():
    now = datetime(2026, 1, 15, 6, 30, 0, tzinfo=IST)
    seconds = seconds_until_next_run(now)
    assert seconds == 2.5 * 3600  # 06:30 -> 09:00 today


def test_after_9am_waits_until_9am_tomorrow():
    now = datetime(2026, 1, 15, 14, 0, 0, tzinfo=IST)
    seconds = seconds_until_next_run(now)
    assert seconds == 19 * 3600  # 14:00 today -> 09:00 tomorrow


def test_exactly_9am_waits_a_full_day():
    now = datetime(2026, 1, 15, 9, 0, 0, tzinfo=IST)
    seconds = seconds_until_next_run(now)
    assert seconds == 24 * 3600
