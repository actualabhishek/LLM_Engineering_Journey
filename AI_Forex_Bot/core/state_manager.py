"""
core/state_manager.py
---------------------
Lightweight JSON-based state manager.
Replaces any database dependency.
All reads/writes are atomic using temp-file swap pattern.
Execution engine is NEVER blocked by storage operations.

Files managed:
  storage/data/active_trades.json    - currently open trades
  storage/data/trade_history.csv     - completed trades (append-only)
  storage/data/daily_stats.json      - today's P&L, drawdown tracking
  storage/data/ai_logs.json          - last N AI decisions (ring buffer)
"""

import csv
import json
import os
import tempfile
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "storage" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ACTIVE_TRADES_FILE = DATA_DIR / "active_trades.json"
TRADE_HISTORY_FILE = DATA_DIR / "trade_history.csv"
DAILY_STATS_FILE = DATA_DIR / "daily_stats.json"
AI_LOG_FILE = DATA_DIR / "ai_logs.json"

HISTORY_COLUMNS = [
    "ticket", "pair", "direction", "lot_size", "open_time", "close_time",
    "open_price", "close_price", "sl", "tp", "profit_usd", "pips",
    "confidence", "session", "exit_reason"
]

_lock = threading.Lock()  # Global lock for file writes


def _atomic_write(path: Path, data: Any) -> None:
    """Write JSON atomically via temp file swap to prevent corruption."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _read_json(path: Path, default: Any = None) -> Any:
    """Read JSON file safely; return default if missing or corrupt."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


# ============================================================
# Active Trades
# ============================================================

def get_active_trades() -> Dict[str, Dict]:
    """Return dict of {ticket_str: trade_dict} for open positions."""
    return _read_json(ACTIVE_TRADES_FILE, default={})


def save_active_trade(ticket: int, trade_data: Dict) -> None:
    """Add or update a trade in active_trades.json."""
    with _lock:
        trades = get_active_trades()
        trades[str(ticket)] = {**trade_data, "ticket": ticket}
        _atomic_write(ACTIVE_TRADES_FILE, trades)


def remove_active_trade(ticket: int) -> Optional[Dict]:
    """Remove and return a closed trade from active_trades.json."""
    with _lock:
        trades = get_active_trades()
        removed = trades.pop(str(ticket), None)
        _atomic_write(ACTIVE_TRADES_FILE, trades)
    return removed


def count_active_trades() -> int:
    return len(get_active_trades())


def get_active_trade(ticket: int) -> Optional[Dict]:
    return get_active_trades().get(str(ticket))


# ============================================================
# Trade History (CSV append-only)
# ============================================================

def append_trade_history(trade: Dict) -> None:
    """Append closed trade to CSV. Creates file with header if new."""
    with _lock:
        file_exists = TRADE_HISTORY_FILE.exists()
        try:
            with open(TRADE_HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS, extrasaction="ignore")
                if not file_exists:
                    writer.writeheader()
                writer.writerow(trade)
        except Exception:
            pass  # Never block on CSV failure


def load_trade_history(days: int = 30) -> List[Dict]:
    """Load recent trade history from CSV."""
    try:
        rows = []
        with open(TRADE_HISTORY_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows[-500:] if len(rows) > 500 else rows  # cap at 500
    except FileNotFoundError:
        return []


# ============================================================
# Daily Statistics
# ============================================================

def get_daily_stats() -> Dict:
    """Return today's stats. Resets automatically on new day."""
    stats = _read_json(DAILY_STATS_FILE, default={})
    today = date.today().isoformat()
    if stats.get("date") != today:
        # New day - reset stats
        stats = {
            "date": today,
            "trades_taken": 0,
            "trades_won": 0,
            "trades_lost": 0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "net_pnl": 0.0,
            "peak_balance": 0.0,
            "current_drawdown_pct": 0.0,
            "pairs_traded": [],
            "last_trade_time": None,
            "last_trade_time_by_pair": {},
        }
        _atomic_write(DAILY_STATS_FILE, stats)
    return stats


def update_daily_stats(profit: float, pair: str, won: bool, **kwargs) -> None:
    """Update daily stats after a trade closes."""
    with _lock:
        stats = get_daily_stats()
        stats["trades_taken"] += 1
        if won:
            stats["trades_won"] += 1
            stats["gross_profit"] += profit
        else:
            stats["trades_lost"] += 1
            stats["gross_loss"] += abs(profit)
        stats["net_pnl"] += profit
        now_iso = datetime.now(timezone.utc).isoformat()
        stats["last_trade_time"] = now_iso
        if "last_trade_time_by_pair" not in stats:
            stats["last_trade_time_by_pair"] = {}
        stats["last_trade_time_by_pair"][pair] = now_iso
        # Store score for cooldown tier logic
        if "last_trade_score_by_pair" not in stats:
            stats["last_trade_score_by_pair"] = {}
        if "score" in kwargs:
            stats["last_trade_score_by_pair"][pair] = kwargs["score"]
        if pair not in stats["pairs_traded"]:
            stats["pairs_traded"].append(pair)
        _atomic_write(DAILY_STATS_FILE, stats)


def update_drawdown(current_balance: float, peak_balance: float) -> None:
    """Track real-time drawdown."""
    with _lock:
        stats = get_daily_stats()
        if current_balance > peak_balance:
            stats["peak_balance"] = current_balance
        if stats["peak_balance"] > 0:
            dd = (stats["peak_balance"] - current_balance) / stats["peak_balance"] * 100
            stats["current_drawdown_pct"] = round(dd, 2)
        _atomic_write(DAILY_STATS_FILE, stats)


# ============================================================
# AI Decision Ring Buffer (last 100 decisions)
# ============================================================

AI_LOG_MAX = 100

def save_ai_decision(record: Dict) -> None:
    """Save AI decision to ring buffer JSON."""
    with _lock:
        logs = _read_json(AI_LOG_FILE, default=[])
        if not isinstance(logs, list):
            logs = []
        logs.append({**record, "ts": datetime.now(timezone.utc).isoformat()})
        if len(logs) > AI_LOG_MAX:
            logs = logs[-AI_LOG_MAX:]
        _atomic_write(AI_LOG_FILE, logs)


def get_ai_decisions(n: int = 20) -> List[Dict]:
    logs = _read_json(AI_LOG_FILE, default=[])
    return logs[-n:] if isinstance(logs, list) else []


# ============================================================
# Kill Switch
# ============================================================

KILL_SWITCH_FILE = DATA_DIR / "kill_switch.json"

def is_kill_switch_active() -> bool:
    data = _read_json(KILL_SWITCH_FILE, default={"active": False})
    return bool(data.get("active", False))


def set_kill_switch(active: bool, reason: str = "") -> None:
    with _lock:
        _atomic_write(KILL_SWITCH_FILE, {
            "active": active,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
