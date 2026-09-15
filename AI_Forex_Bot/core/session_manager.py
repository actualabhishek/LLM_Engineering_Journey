"""
core/session_manager.py
-----------------------
Forex session detection and timing utilities.
Determines:
  - Current trading session (London, NY, Asian, Off)
  - Whether overlap session is active
  - Minimum confidence threshold for current session
  - Whether trading is allowed right now
"""

from datetime import datetime, time, timezone
from enum import Enum
from typing import Dict, Tuple

from core.config_manager import config
from core.logger import get_logger

logger = get_logger(__name__)


class Session(Enum):
    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "london_ny_overlap"
    OFF = "off"


def _parse_time(t_str: str) -> time:
    """Parse 'HH:MM' string to time object."""
    h, m = map(int, t_str.split(":"))
    return time(h, m)


def get_current_session(dt: datetime = None) -> Session:
    """
    Return the primary session for the given UTC datetime.
    Priority: OVERLAP > LONDON > NEW_YORK > ASIAN > OFF
    """
    if dt is None:
        dt = datetime.now(timezone.utc)

    current = dt.time().replace(second=0, microsecond=0)
    cfg = config.get("sessions")

    london_start = _parse_time(cfg["london"]["start_utc"])
    london_end   = _parse_time(cfg["london"]["end_utc"])
    ny_start     = _parse_time(cfg["new_york"]["start_utc"])
    ny_end       = _parse_time(cfg["new_york"]["end_utc"])
    overlap_start = _parse_time(cfg["overlap"]["start_utc"])
    overlap_end   = _parse_time(cfg["overlap"]["end_utc"])
    asian_start  = _parse_time(cfg["asian"]["start_utc"])
    asian_end    = _parse_time(cfg["asian"]["end_utc"])

    def in_range(t: time, start: time, end: time) -> bool:
        if start < end:
            return start <= t < end
        # Crosses midnight
        return t >= start or t < end

    # Check overlap first (highest priority)
    if in_range(current, overlap_start, overlap_end):
        return Session.OVERLAP

    if in_range(current, london_start, london_end):
        return Session.LONDON

    if in_range(current, ny_start, ny_end):
        return Session.NEW_YORK

    if in_range(current, asian_start, asian_end):
        return Session.ASIAN

    return Session.OFF


def get_session_info(dt: datetime = None) -> Dict:
    """Return full session context dict for use in decision engine."""
    session = get_current_session(dt)
    cfg = config.get("sessions")

    min_confidence = cfg.get("off_session_min_confidence", 80)
    is_aggressive = False
    is_allowed = True

    if session == Session.OVERLAP:
        min_confidence = 60
        is_aggressive = True
    elif session in (Session.LONDON, Session.NEW_YORK):
        min_confidence = 65
        is_aggressive = True
    elif session == Session.ASIAN:
        min_confidence = cfg["asian"].get("min_confidence", 80)
        is_aggressive = False
    else:
        min_confidence = cfg.get("off_session_min_confidence", 80)
        is_aggressive = False

    return {
        "session": session.value,
        "is_aggressive": is_aggressive,
        "is_overlap": session == Session.OVERLAP,
        "min_confidence_required": min_confidence,
        "trading_allowed": is_allowed,
    }


def is_trading_time(dt: datetime = None) -> Tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).
    False only when session is OFF and no special condition.
    """
    info = get_session_info(dt)
    session = info["session"]

    if session == Session.OFF.value:
        return False, "Outside all major sessions"

    return True, f"Session: {session}"


def get_best_pairs_for_session(session: Session) -> list:
    """
    Return pairs most active during the given session.
    Trimmed to the live 2-pair universe (EURUSD/GBPUSD) — currently unused
    elsewhere, kept for future pair-prioritization use.
    """
    session_pairs = {
        Session.LONDON: ["GBPUSD", "EURUSD"],
        Session.NEW_YORK: ["EURUSD", "GBPUSD"],
        Session.OVERLAP: ["EURUSD", "GBPUSD"],
        Session.ASIAN: [],
        Session.OFF: [],
    }
    return session_pairs.get(session, [])
