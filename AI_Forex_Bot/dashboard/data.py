"""
dashboard/data.py
------------------
All data-access functions for the dashboard, split out of the old
monolithic app.py. Pure I/O — no Streamlit rendering here. Loaders that hit
local files keep their original @st.cache_data behavior; live MT5 calls stay
uncached (positions/account/candles need to be fresh every refresh).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "storage" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Generic file loaders ────────────────────────────────────────────────────

def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def load_csv(path):
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


# ── Cached local-file loaders (unchanged behavior from the old app.py) ─────

@st.cache_data(ttl=5)
def load_daily_stats():
    return load_json(DATA_DIR / "daily_stats.json", {})


@st.cache_data(ttl=5)
def load_ai_decisions():
    return load_json(DATA_DIR / "ai_logs.json", [])


@st.cache_data(ttl=5)
def load_kill_switch():
    d = load_json(DATA_DIR / "kill_switch.json", {})
    return d.get("active", False), d.get("reason", "")


@st.cache_data(ttl=10)
def load_trade_history():
    df = load_csv(DATA_DIR / "trade_history.csv")
    if df.empty:
        return df
    for col in ["profit_usd", "pips", "confidence"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "close_time" in df.columns:
        df["close_time"] = pd.to_datetime(df["close_time"], errors="coerce", utc=True)
    if "open_time" in df.columns:
        df["open_time"] = pd.to_datetime(df["open_time"], errors="coerce", utc=True)
    return df


# ── Live MT5 loaders (uncached — must reflect the current tick) ────────────

def load_mt5_positions():
    """Pull live open positions directly from MT5."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return []
        positions = mt5.positions_get()
        if positions is None:
            return []
        result = []
        for p in positions:
            tick = mt5.symbol_info_tick(p.symbol)
            current_price = tick.bid if p.type == 1 else tick.ask if tick else p.price_open
            pip = 0.01 if "JPY" in p.symbol else 0.0001
            floating_pips = ((current_price - p.price_open) / pip) if p.type == 0 else ((p.price_open - current_price) / pip)
            sl_distance   = abs(p.price_open - p.sl) / pip if p.sl else 0
            tp_distance   = abs(p.tp - p.price_open) / pip if p.tp else 0
            moved_pips    = abs(current_price - p.price_open) / pip
            sl_progress   = min(100, (moved_pips / sl_distance * 100)) if sl_distance > 0 else 0
            tp_progress   = min(100, (moved_pips / tp_distance * 100)) if tp_distance > 0 else 0
            open_dt       = datetime.fromtimestamp(p.time, tz=timezone.utc)
            duration_min  = int((datetime.now(timezone.utc) - open_dt).total_seconds() / 60)
            result.append({
                "ticket":        p.ticket,
                "pair":          p.symbol,
                "direction":     "BUY" if p.type == 0 else "SELL",
                "lots":          p.volume,
                "open_price":    round(p.price_open, 5),
                "current_price": round(current_price, 5),
                "sl":            round(p.sl, 5) if p.sl else None,
                "tp":            round(p.tp, 5) if p.tp else None,
                "floating_pnl":  round(p.profit, 2),
                "floating_pips": round(floating_pips, 1),
                "sl_pips":       round(sl_distance, 1),
                "tp_pips":       round(tp_distance, 1),
                "sl_progress":   round(sl_progress, 1),
                "tp_progress":   round(tp_progress, 1),
                "duration_min":  duration_min,
            })
        return result
    except Exception:
        # Fallback: read from active_trades.json if MT5 not available
        # (e.g. running on Linux/Docker, where the MetaTrader5 package is
        # stripped from requirements — see Dockerfile).
        trades = load_json(DATA_DIR / "active_trades.json", {})
        return list(trades.values()) if trades else []


def load_mt5_account():
    """Pull live account info from MT5."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return {}
        info = mt5.account_info()
        if not info:
            return {}
        return {
            "balance":     info.balance,
            "equity":      info.equity,
            "margin":      info.margin,
            "free_margin": info.margin_free,
            "profit":      info.profit,
            "leverage":    getattr(info, "leverage", None),
        }
    except Exception:
        return {}


def load_candles_with_indicators(pair: str, timeframe: str = "M15", count: int = 150):
    """
    Fetch recent candles plus EMA9/21/50 and Supertrend overlays for the
    candlestick chart. Computed directly with pandas_ta across the whole
    window (unlike strategies.indicators.calculate_indicators, which only
    returns the single last-row snapshot the trading engine needs).
    Returns None if MT5/candle data is unavailable.
    """
    try:
        import MetaTrader5 as mt5
        import pandas_ta as ta

        if not mt5.initialize():
            return None
        tf_map = {"M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1}
        tf = tf_map.get(timeframe, mt5.TIMEFRAME_M15)
        fetch_count = max(count, 60) + 55  # pad for EMA50 warmup
        rates = mt5.copy_rates_from_pos(pair, tf, 0, fetch_count)
        if rates is None or len(rates) == 0:
            return None

        df = pd.DataFrame(rates)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)
        df = df[["open", "high", "low", "close", "volume"]]

        df["ema9"] = ta.ema(df["close"], length=9)
        df["ema21"] = ta.ema(df["close"], length=21)
        df["ema50"] = ta.ema(df["close"], length=50)
        st_df = ta.supertrend(df["high"], df["low"], df["close"], length=10, multiplier=3.0)
        if st_df is not None:
            df["supertrend"] = st_df.iloc[:, 0]

        return df.tail(count)
    except Exception:
        return None


def get_session_and_mtf_snapshot(pair: str):
    """
    Lightweight, dashboard-only read of the current session quality and a
    rough MTF bias for `pair` — reuses core.session_manager as the single
    source of truth (the old app.py had its own slightly-divergent ad-hoc
    get_session(hour) re-implementation).
    """
    try:
        from core.session_manager import get_session_info
        return get_session_info()
    except Exception:
        return {"session": "unknown", "is_aggressive": False, "min_confidence_required": None}
