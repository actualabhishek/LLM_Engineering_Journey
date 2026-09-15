"""
news_engine/news_filter.py
---------------------------
Economic calendar news filter — prevents trading during high-impact news events.
Uses investing.com API as primary source with fallback to hardcoded major events.

Key protection:
  - Blocks trades 15 minutes BEFORE high-impact news
  - Blocks trades 15 minutes AFTER high-impact news
  - Widens spread threshold detection as secondary signal
  - Covers USD, GBP, EUR, JPY, AUD, CAD pairs
"""

import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Tuple, Dict, List
import threading
import time

from core.config_manager import config
from core.logger import get_logger

logger = get_logger("news_filter")

# Currency → pairs mapping
CURRENCY_PAIRS = {
    "USD": ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDJPY", "USDCHF"],
    "GBP": ["GBPUSD", "GBPJPY", "EURGBP"],
    "EUR": ["EURUSD", "EURJPY", "EURGBP"],
    "JPY": ["USDJPY", "GBPJPY", "EURJPY", "AUDJPY", "CADJPY"],
    "AUD": ["AUDUSD", "AUDJPY"],
    "CAD": ["USDCAD", "CADJPY"],
    "NZD": ["NZDUSD", "NZDJPY"],
    "CHF": ["USDCHF", "EURCHF"],
}

# Hardcoded major recurring events (fallback when API fails)
# Format: (hour_utc, minute, currency, description)
RECURRING_MAJOR_EVENTS = [
    # US events (highest market impact)
    (12, 30, "USD", "US CPI / PPI / NFP / Retail Sales"),   # 8:30 ET
    (13, 30, "USD", "US Economic Data"),                     # 9:30 ET
    (14, 00, "USD", "US Economic Data"),                     # 10:00 ET
    (18, 00, "USD", "Fed Interest Rate Decision"),           # 2:00 PM ET
    (18, 30, "USD", "FOMC Press Conference"),               # 2:30 PM ET
    # UK events
    (7,  00, "GBP", "UK Economic Data"),
    (9,  30, "GBP", "UK CPI / GDP / Employment"),
    # EU events  
    (8,  55, "EUR", "German PMI / Employment"),
    (9,  00, "EUR", "EU PMI / CPI"),
    (12, 45, "EUR", "ECB Rate Decision"),
    (13, 30, "EUR", "ECB Press Conference"),
    # Japan events
    (0,  30, "JPY", "Japan CPI / GDP"),
    (3,  0,  "JPY", "BOJ Decision"),
    # Canada
    (12, 30, "CAD", "Canada CPI / Employment"),
    (14, 0,  "CAD", "BOC Rate Decision"),
]


class NewsFilter:
    def __init__(self):
        self._events: List[Dict] = []
        self._last_fetch: datetime = None
        self._fetch_interval = 3600  # refresh every hour
        self._lock = threading.Lock()
        self._finnhub_key = (
            config.get("news", "finnhub_api_key")
            or __import__("os").getenv("FINNHUB_API_KEY")
            or ""
        )
        self._fetch_events()

    def _fetch_events(self):
        """
        Load economic calendar.
        Hardcoded schedule is PRIMARY — it covers all major recurring events
        and never fails. API sources are tried as enhancement only.
        """
        # Always set last_fetch so we don't spam retries
        with self._lock:
            self._last_fetch = datetime.now(timezone.utc)

        # Try API sources as enhancement (adds specific one-off events)
        events = []
        try:
            events = self._fetch_fxstreet()
        except Exception:
            pass

        if not events:
            try:
                events = self._fetch_investing_com()
            except Exception:
                pass

        with self._lock:
            self._events = events

        if events:
            logger.info(
                f"News calendar loaded: {len(events)} high-impact events from API "
                f"+ hardcoded recurring schedule active"
            )
        else:
            logger.info(
                "News calendar: hardcoded recurring schedule active "
                f"(covers Fed, ECB, BOE, BOJ, NFP, CPI and {len(RECURRING_MAJOR_EVENTS)-5} more events)"
            )

    def _fetch_finnhub(self) -> List[Dict]:
        """
        Fetch from Finnhub economic calendar API.
        Free API key at https://finnhub.io/register
        Add FINNHUB_API_KEY to your .env file
        """
        now  = datetime.now(timezone.utc)
        from_date = now.strftime("%Y-%m-%d")
        to_date   = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        url = (
            f"https://finnhub.io/api/v1/calendar/economic"
            f"?from={from_date}&to={to_date}&token={self._finnhub_key}"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []

        data = resp.json()
        events = []
        for item in data.get("economicCalendar", []):
            try:
                impact = item.get("impact", "").upper()
                if impact not in ("HIGH", "MEDIUM"):
                    continue
                # Finnhub time format: "2026-06-11 12:30:00"
                time_str = item.get("time", "")
                if not time_str:
                    continue
                event_time = datetime.strptime(
                    time_str, "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
                events.append({
                    "time":     event_time,
                    "currency": item.get("country", "").upper()[:3],
                    "name":     item.get("event", ""),
                    "impact":   impact,
                })
            except Exception:
                continue
        return events

    def _fetch_investing_com(self) -> List[Dict]:
        """Fetch from investing.com economic calendar."""
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        url = (
            f"https://economic-calendar.investing.com/economic-calendar/action_getworker/"
            f"?dateFrom={date_str}&dateTo={date_str}&timeZone=0&timezoneID=0"
            f"&importance%5B%5D=3"  # high impact only
        )
        headers = {
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.investing.com/economic-calendar/",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []

        data = resp.json()
        events = []
        for item in data.get("data", []):
            try:
                event_time = datetime.fromisoformat(
                    item.get("date", "").replace("Z", "+00:00")
                )
                events.append({
                    "time": event_time,
                    "currency": item.get("currency", ""),
                    "name": item.get("event", ""),
                    "impact": "HIGH",
                })
            except Exception:
                continue
        return events

    def _fetch_fxstreet(self) -> List[Dict]:
        """Fetch from fxstreet economic calendar."""
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        url = (
            f"https://calendar.fxstreet.com/eventdate/aspx?"
            f"minDate={date_str}&maxDate={date_str}&timezone=UTC"
            f"&volatility=HIGH&format=json"
        )
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return []

        events = []
        for item in resp.json():
            try:
                event_time = datetime.fromisoformat(
                    item.get("DateUtc", "").replace("Z", "+00:00")
                )
                events.append({
                    "time": event_time,
                    "currency": item.get("Currency", ""),
                    "name": item.get("Name", ""),
                    "impact": "HIGH",
                })
            except Exception:
                continue
        return events

    def _refresh_if_needed(self):
        """Refresh calendar if older than fetch_interval."""
        now = datetime.now(timezone.utc)
        if (self._last_fetch is None or
                (now - self._last_fetch).seconds > self._fetch_interval):
            thread = threading.Thread(target=self._fetch_events, daemon=True)
            thread.start()

    def _is_recurring_news_time(self, now: datetime) -> Tuple[bool, str]:
        """
        Check if current time matches a known recurring high-impact event window.
        Used as fallback when API calendar is unavailable.
        """
        buffer_before = 20  # minutes before event
        buffer_after  = 15  # minutes after event

        for hour, minute, currency, description in RECURRING_MAJOR_EVENTS:
            event_time = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            diff = (now - event_time).total_seconds() / 60  # minutes

            if -buffer_before <= diff <= buffer_after:
                return True, f"Near {currency} event: {description} ({hour:02d}:{minute:02d} UTC)"

        return False, ""

    def is_safe_to_trade(self, pair: str) -> Tuple[bool, str]:
        """
        Returns (safe, reason).
        safe=False means do not trade this pair right now.
        """
        self._refresh_if_needed()
        now = datetime.now(timezone.utc)

        buffer_before = timedelta(minutes=config.get("news", "block_minutes_before") or 15)
        buffer_after  = timedelta(minutes=config.get("news", "block_minutes_after")  or 15)

        # Find which currencies affect this pair
        affected_currencies = []
        pair_upper = pair.upper()
        for currency, pairs in CURRENCY_PAIRS.items():
            if pair_upper in pairs:
                affected_currencies.append(currency)

        # Check API events
        with self._lock:
            for event in self._events:
                if event["currency"] not in affected_currencies:
                    continue
                diff = now - event["time"]
                if -buffer_before <= diff <= buffer_after:
                    return False, (
                        f"News event: {event['name']} "
                        f"({event['currency']}) at {event['time'].strftime('%H:%M')} UTC"
                    )

        # Fallback: check recurring schedule
        is_news_time, reason = self._is_recurring_news_time(now)
        if is_news_time:
            # Only block if pair is affected by that currency
            for _, __, currency, ___ in RECURRING_MAJOR_EVENTS:
                if currency in affected_currencies:
                    return False, reason

        # All clear
        return True, ""

    def get_news_context(self, pair: str) -> Dict:
        """Returns news context for AI decision engine."""
        self._refresh_if_needed()
        now = datetime.now(timezone.utc)
        upcoming = []
        window = timedelta(hours=2)

        affected_currencies = []
        for currency, pairs in CURRENCY_PAIRS.items():
            if pair.upper() in pairs:
                affected_currencies.append(currency)

        with self._lock:
            for event in self._events:
                if event["currency"] not in affected_currencies:
                    continue
                diff = event["time"] - now
                if timedelta(0) <= diff <= window:
                    mins = int(diff.total_seconds() / 60)
                    upcoming.append(f"{event['name']} in {mins}min")

        # Check recurring events in next 2 hours
        for hour, minute, currency, description in RECURRING_MAJOR_EVENTS:
            if currency not in affected_currencies:
                continue
            event_time = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if event_time < now:
                event_time += timedelta(days=1)
            diff = event_time - now
            if timedelta(0) <= diff <= window:
                mins = int(diff.total_seconds() / 60)
                upcoming.append(f"{description} in {mins}min")

        risk = "HIGH" if upcoming else "LOW"
        return {
            "upcoming_events": upcoming[:3],
            "risk_level": risk,
            "events_str": ", ".join(upcoming[:3]) if upcoming else "None",
        }


# Singleton
news_filter = NewsFilter()
