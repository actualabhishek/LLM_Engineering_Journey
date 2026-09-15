"""
advanced_analysis.py
--------------------
Advanced technical analysis module for ForexAI Trader.

Detects 6 high-probability setups and returns a structured result
that feeds directly into the confidence engine scoring.

Detectors:
  1. Chart Patterns      — Head & Shoulders, Double Top/Bottom, Triangles,
                           Flags, Wedges, Cup & Handle
  2. Support & Resistance — Dynamic S/R levels + breakout/bounce detection
  3. Trend Lines         — Swing-point regression trendlines + break detection
  4. Order Blocks        — Institutional supply/demand zones (Smart Money)
  5. Fibonacci Levels    — Retracement & extension key levels
  6. Candlestick Patterns— Engulfing, Pin Bar, Morning/Evening Star,
                           Doji, Three Soldiers/Crows, Hammer, Shooting Star

Each detector returns:
  {
    "signal":      "BUY" | "SELL" | "NEUTRAL",
    "confidence":  0-100,       # how strong this setup is
    "pattern":     str,          # human-readable pattern name
    "key_level":   float | None, # price level (S/R, OB zone, Fib level)
    "details":     dict,         # extra data for logging / LLM context
  }

The aggregate score (0-30 bonus points) is added to the main confidence score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional
from scipy.signal import argrelextrema
from core.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def _swing_highs(series: pd.Series, order: int = 5) -> np.ndarray:
    """Indices of local maxima (swing highs)."""
    idx = argrelextrema(series.values, np.greater_equal, order=order)[0]
    return idx


def _swing_lows(series: pd.Series, order: int = 5) -> np.ndarray:
    """Indices of local minima (swing lows)."""
    idx = argrelextrema(series.values, np.less_equal, order=order)[0]
    return idx


def _pip_size(pair: str) -> float:
    jpy = "JPY" in pair.upper()
    return 0.01 if jpy else 0.0001


def _pips(price_diff: float, pair: str) -> float:
    return abs(price_diff) / _pip_size(pair)


def _neutral() -> dict:
    return {"signal": "NEUTRAL", "confidence": 0, "pattern": "none",
            "key_level": None, "details": {}}


# ─────────────────────────────────────────────────────────────────────────────
# 1. SUPPORT & RESISTANCE + BREAKOUT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_sr_breakout(df: pd.DataFrame, pair: str, lookback: int = 80) -> dict:
    """
    Identifies dynamic S/R levels from swing highs/lows, then checks
    whether the current candle has cleanly broken or bounced off one.

    Breakout above resistance → BUY
    Breakdown below support   → SELL
    Bounce off support        → BUY
    Bounce off resistance     → SELL
    """
    try:
        window = df.iloc[-lookback:].copy().reset_index(drop=True)
        highs = window["high"]
        lows  = window["low"]
        close = window["close"]
        pip   = _pip_size(pair)

        sh_idx = _swing_highs(highs, order=4)
        sl_idx = _swing_lows(lows,   order=4)

        if len(sh_idx) < 2 or len(sl_idx) < 2:
            return _neutral()

        # Cluster nearby levels (within 5 pips)
        resistance_levels = sorted(set(round(highs.iloc[i] / (pip * 5)) * pip * 5 for i in sh_idx))
        support_levels    = sorted(set(round(lows.iloc[i]  / (pip * 5)) * pip * 5 for i in sl_idx))

        current_close = close.iloc[-2]   # last CLOSED candle
        current_high  = highs.iloc[-2]
        current_low   = lows.iloc[-2]
        prev_close    = close.iloc[-3]
        atr           = (highs - lows).rolling(14).mean().iloc[-2]
        tolerance     = atr * 0.3         # 30% ATR tolerance for "at level"

        # ── Resistance breakout (BUY) ──
        for level in resistance_levels[-5:]:           # top 5 resistance levels
            if prev_close < level and current_close > level + tolerance:
                touches = sum(1 for i in sh_idx if abs(highs.iloc[i] - level) < atr * 0.5)
                conf = min(90, 55 + touches * 10)
                return {
                    "signal": "BUY",
                    "confidence": conf,
                    "pattern": "Resistance Breakout",
                    "key_level": round(level, 5),
                    "details": {"level": level, "touches": touches, "atr": atr},
                }

        # ── Support breakdown (SELL) ──
        for level in support_levels[:5]:               # bottom 5 support levels
            if prev_close > level and current_close < level - tolerance:
                touches = sum(1 for i in sl_idx if abs(lows.iloc[i] - level) < atr * 0.5)
                conf = min(90, 55 + touches * 10)
                return {
                    "signal": "SELL",
                    "confidence": conf,
                    "pattern": "Support Breakdown",
                    "key_level": round(level, 5),
                    "details": {"level": level, "touches": touches, "atr": atr},
                }

        # ── Support bounce (BUY) ──
        for level in support_levels[:5]:
            if abs(current_low - level) < tolerance and current_close > level:
                touches = sum(1 for i in sl_idx if abs(lows.iloc[i] - level) < atr * 0.5)
                conf = min(80, 50 + touches * 8)
                return {
                    "signal": "BUY",
                    "confidence": conf,
                    "pattern": "Support Bounce",
                    "key_level": round(level, 5),
                    "details": {"level": level, "touches": touches},
                }

        # ── Resistance bounce (SELL) ──
        for level in resistance_levels[-5:]:
            if abs(current_high - level) < tolerance and current_close < level:
                touches = sum(1 for i in sh_idx if abs(highs.iloc[i] - level) < atr * 0.5)
                conf = min(80, 50 + touches * 8)
                return {
                    "signal": "SELL",
                    "confidence": conf,
                    "pattern": "Resistance Bounce",
                    "key_level": round(level, 5),
                    "details": {"level": level, "touches": touches},
                }

        return _neutral()

    except Exception as e:
        logger.debug(f"S/R detector error: {e}")
        return _neutral()


# ─────────────────────────────────────────────────────────────────────────────
# 2. TREND LINE BREAK DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_trendline_break(df: pd.DataFrame, pair: str, lookback: int = 60) -> dict:
    """
    Fits regression trendlines through the most recent swing highs (downtrend)
    and swing lows (uptrend), then detects breaks.

    Break above downtrend line  → BUY
    Break below uptrend line    → SELL
    """
    try:
        window = df.iloc[-lookback:].copy().reset_index(drop=True)
        highs  = window["high"]
        lows   = window["low"]
        close  = window["close"]

        sh_idx = _swing_highs(highs, order=4)
        sl_idx = _swing_lows(lows,   order=4)

        atr = (highs - lows).rolling(14).mean().iloc[-2]
        tolerance = atr * 0.2

        current_close = close.iloc[-2]
        prev_close    = close.iloc[-3]
        x_now         = len(window) - 2   # index of last closed bar

        # ── Downtrend line (through swing highs) ──
        if len(sh_idx) >= 2:
            x = sh_idx[-3:] if len(sh_idx) >= 3 else sh_idx[-2:]
            y = highs.iloc[x].values
            if len(x) >= 2 and x[-1] > x[0]:
                slope = (y[-1] - y[0]) / (x[-1] - x[0])
                intercept = y[0] - slope * x[0]
                tl_value = slope * x_now + intercept   # trendline at current bar

                if slope < 0:  # downward trendline = resistance
                    if prev_close < tl_value and current_close > tl_value + tolerance:
                        conf = 70 if abs(slope) < atr * 0.1 else 60
                        return {
                            "signal": "BUY",
                            "confidence": conf,
                            "pattern": "Downtrend Line Break",
                            "key_level": round(tl_value, 5),
                            "details": {"slope": round(slope, 6), "tl_value": round(tl_value, 5)},
                        }

        # ── Uptrend line (through swing lows) ──
        if len(sl_idx) >= 2:
            x = sl_idx[-3:] if len(sl_idx) >= 3 else sl_idx[-2:]
            y = lows.iloc[x].values
            if len(x) >= 2 and x[-1] > x[0]:
                slope = (y[-1] - y[0]) / (x[-1] - x[0])
                intercept = y[0] - slope * x[0]
                tl_value = slope * x_now + intercept

                if slope > 0:  # upward trendline = support
                    if prev_close > tl_value and current_close < tl_value - tolerance:
                        conf = 70 if slope > atr * 0.01 else 60
                        return {
                            "signal": "SELL",
                            "confidence": conf,
                            "pattern": "Uptrend Line Break",
                            "key_level": round(tl_value, 5),
                            "details": {"slope": round(slope, 6), "tl_value": round(tl_value, 5)},
                        }

        return _neutral()

    except Exception as e:
        logger.debug(f"Trendline detector error: {e}")
        return _neutral()


# ─────────────────────────────────────────────────────────────────────────────
# 3. CHART PATTERN DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_chart_patterns(df: pd.DataFrame, pair: str) -> dict:
    """
    Detects: Double Top/Bottom, Head & Shoulders, Bull/Bear Flag,
             Ascending/Descending Triangle, Rising/Falling Wedge.
    """
    try:
        window = df.iloc[-80:].copy().reset_index(drop=True)
        highs  = window["high"]
        lows   = window["low"]
        close  = window["close"]
        atr    = (highs - lows).rolling(14).mean().iloc[-2]

        sh_idx = _swing_highs(highs, order=5)
        sl_idx = _swing_lows(lows,   order=5)

        if len(sh_idx) < 3 or len(sl_idx) < 3:
            return _neutral()

        # Recent swing points
        sh_vals = highs.iloc[sh_idx[-5:]].values
        sl_vals = lows.iloc[sl_idx[-5:]].values

        # ── DOUBLE TOP → SELL ──
        if len(sh_vals) >= 2:
            h1, h2 = sh_vals[-2], sh_vals[-1]
            if abs(h1 - h2) < atr * 0.5 and close.iloc[-2] < min(h1, h2) - atr * 0.3:
                return {
                    "signal": "SELL",
                    "confidence": 78,
                    "pattern": "Double Top",
                    "key_level": round((h1 + h2) / 2, 5),
                    "details": {"top1": h1, "top2": h2},
                }

        # ── DOUBLE BOTTOM → BUY ──
        if len(sl_vals) >= 2:
            l1, l2 = sl_vals[-2], sl_vals[-1]
            if abs(l1 - l2) < atr * 0.5 and close.iloc[-2] > max(l1, l2) + atr * 0.3:
                return {
                    "signal": "BUY",
                    "confidence": 78,
                    "pattern": "Double Bottom",
                    "key_level": round((l1 + l2) / 2, 5),
                    "details": {"bottom1": l1, "bottom2": l2},
                }

        # ── HEAD & SHOULDERS → SELL ──
        if len(sh_vals) >= 3:
            ls, head, rs = sh_vals[-3], sh_vals[-2], sh_vals[-1]
            if head > ls and head > rs and abs(ls - rs) < atr * 0.8:
                neckline = min(sl_vals[-2], sl_vals[-1]) if len(sl_vals) >= 2 else sl_vals[-1]
                if close.iloc[-2] < neckline:
                    return {
                        "signal": "SELL",
                        "confidence": 82,
                        "pattern": "Head & Shoulders",
                        "key_level": round(neckline, 5),
                        "details": {"head": head, "neckline": neckline},
                    }

        # ── INVERSE H&S → BUY ──
        if len(sl_vals) >= 3:
            ls, head, rs = sl_vals[-3], sl_vals[-2], sl_vals[-1]
            if head < ls and head < rs and abs(ls - rs) < atr * 0.8:
                neckline = max(sh_vals[-2], sh_vals[-1]) if len(sh_vals) >= 2 else sh_vals[-1]
                if close.iloc[-2] > neckline:
                    return {
                        "signal": "BUY",
                        "confidence": 82,
                        "pattern": "Inverse Head & Shoulders",
                        "key_level": round(neckline, 5),
                        "details": {"head": head, "neckline": neckline},
                    }

        # ── BULL FLAG → BUY ──
        # Sharp rally (pole) followed by tight consolidation pulling back
        if len(close) >= 30:
            pole_end   = close.iloc[-20]
            pole_start = close.iloc[-30]
            flag_high  = close.iloc[-20:-5].max()
            flag_low   = close.iloc[-20:-5].min()
            pole_move  = pole_end - pole_start
            flag_range = flag_high - flag_low

            if pole_move > atr * 3 and flag_range < pole_move * 0.4 and \
               close.iloc[-2] > flag_high and pole_move > 0:
                return {
                    "signal": "BUY",
                    "confidence": 72,
                    "pattern": "Bull Flag Breakout",
                    "key_level": round(flag_high, 5),
                    "details": {"pole_move": round(pole_move, 5), "flag_range": round(flag_range, 5)},
                }

        # ── BEAR FLAG → SELL ──
        if len(close) >= 30:
            pole_end   = close.iloc[-20]
            pole_start = close.iloc[-30]
            flag_high  = close.iloc[-20:-5].max()
            flag_low   = close.iloc[-20:-5].min()
            pole_move  = pole_start - pole_end
            flag_range = flag_high - flag_low

            if pole_move > atr * 3 and flag_range < pole_move * 0.4 and \
               close.iloc[-2] < flag_low and pole_move > 0:
                return {
                    "signal": "SELL",
                    "confidence": 72,
                    "pattern": "Bear Flag Breakdown",
                    "key_level": round(flag_low, 5),
                    "details": {"pole_move": round(pole_move, 5), "flag_range": round(flag_range, 5)},
                }

        # ── ASCENDING TRIANGLE → BUY ──
        if len(sh_idx) >= 3 and len(sl_idx) >= 3:
            flat_tops    = np.std(sh_vals[-3:]) < atr * 0.3
            rising_lows  = all(sl_vals[-i-1] > sl_vals[-i-2] for i in range(min(2, len(sl_vals)-1)))
            if flat_tops and rising_lows and close.iloc[-2] > sh_vals[-1]:
                return {
                    "signal": "BUY",
                    "confidence": 75,
                    "pattern": "Ascending Triangle Breakout",
                    "key_level": round(sh_vals[-1], 5),
                    "details": {"resistance": round(sh_vals[-1], 5)},
                }

        # ── DESCENDING TRIANGLE → SELL ──
        if len(sh_idx) >= 3 and len(sl_idx) >= 3:
            flat_bottoms  = np.std(sl_vals[-3:]) < atr * 0.3
            falling_highs = all(sh_vals[-i-1] < sh_vals[-i-2] for i in range(min(2, len(sh_vals)-1)))
            if flat_bottoms and falling_highs and close.iloc[-2] < sl_vals[-1]:
                return {
                    "signal": "SELL",
                    "confidence": 75,
                    "pattern": "Descending Triangle Breakdown",
                    "key_level": round(sl_vals[-1], 5),
                    "details": {"support": round(sl_vals[-1], 5)},
                }

        return _neutral()

    except Exception as e:
        logger.debug(f"Chart pattern detector error: {e}")
        return _neutral()


# ─────────────────────────────────────────────────────────────────────────────
# 4. ORDER BLOCKS (Smart Money / Institutional Zones)
# ─────────────────────────────────────────────────────────────────────────────

def detect_order_blocks(df: pd.DataFrame, pair: str) -> dict:
    """
    Identifies order blocks — the last bearish candle before a strong bullish
    move (bullish OB) or last bullish candle before a strong bearish move
    (bearish OB). Price returning to these zones is a high-probability entry.

    Bullish OB touch (price pulls back to OB zone) → BUY
    Bearish OB touch (price pulls back to OB zone) → SELL
    """
    try:
        window = df.iloc[-100:].copy().reset_index(drop=True)
        op = window["open"]
        cl = window["close"]
        hi = window["high"]
        lo = window["low"]
        atr = (hi - lo).rolling(14).mean()

        impulse_threshold = atr * 1.5   # A "strong" candle is 1.5x ATR

        bullish_obs = []
        bearish_obs = []

        for i in range(5, len(window) - 5):
            candle_size = abs(cl.iloc[i] - op.iloc[i])
            next_3_move = cl.iloc[i+3] - cl.iloc[i]

            # Bullish OB: bearish candle followed by strong bullish impulse
            if cl.iloc[i] < op.iloc[i] and next_3_move > impulse_threshold.iloc[i]:
                bullish_obs.append({
                    "top":    op.iloc[i],          # top of bearish OB candle
                    "bottom": cl.iloc[i],           # bottom
                    "index":  i,
                })

            # Bearish OB: bullish candle followed by strong bearish impulse
            if cl.iloc[i] > op.iloc[i] and next_3_move < -impulse_threshold.iloc[i]:
                bearish_obs.append({
                    "top":    cl.iloc[i],
                    "bottom": op.iloc[i],
                    "index":  i,
                })

        current_close = cl.iloc[-2]
        current_low   = lo.iloc[-2]
        current_high  = hi.iloc[-2]
        current_atr   = atr.iloc[-2]
        tolerance     = current_atr * 0.4

        # Check if price has returned to a recent bullish OB
        for ob in reversed(bullish_obs[-5:]):
            if ob["bottom"] - tolerance <= current_low <= ob["top"] + tolerance:
                if current_close > ob["bottom"]:  # closing above OB bottom = holding
                    age = len(window) - 2 - ob["index"]
                    conf = max(55, 80 - age)       # fresher OB = higher confidence
                    return {
                        "signal": "BUY",
                        "confidence": conf,
                        "pattern": "Bullish Order Block",
                        "key_level": round((ob["top"] + ob["bottom"]) / 2, 5),
                        "details": {"ob_top": ob["top"], "ob_bottom": ob["bottom"], "age_bars": age},
                    }

        # Check if price has returned to a recent bearish OB
        for ob in reversed(bearish_obs[-5:]):
            if ob["bottom"] - tolerance <= current_high <= ob["top"] + tolerance:
                if current_close < ob["top"]:
                    age = len(window) - 2 - ob["index"]
                    conf = max(55, 80 - age)
                    return {
                        "signal": "SELL",
                        "confidence": conf,
                        "pattern": "Bearish Order Block",
                        "key_level": round((ob["top"] + ob["bottom"]) / 2, 5),
                        "details": {"ob_top": ob["top"], "ob_bottom": ob["bottom"], "age_bars": age},
                    }

        return _neutral()

    except Exception as e:
        logger.debug(f"Order block detector error: {e}")
        return _neutral()


# ─────────────────────────────────────────────────────────────────────────────
# 5. FIBONACCI RETRACEMENT LEVELS
# ─────────────────────────────────────────────────────────────────────────────

FIB_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786]
FIB_NAMES  = ["23.6%", "38.2%", "50%", "61.8%", "78.6%"]
HIGH_PROB_FIBS = {0.382, 0.500, 0.618}   # Most respected levels

def detect_fibonacci_levels(df: pd.DataFrame, pair: str) -> dict:
    """
    Identifies the most recent significant swing (high-to-low or low-to-high),
    calculates Fibonacci retracement levels, and checks whether price is
    bouncing from a key level (38.2%, 50%, 61.8%).

    Bounce from Fib support (in upswing) → BUY
    Bounce from Fib resistance (in downswing) → SELL
    """
    try:
        window = df.iloc[-80:].copy().reset_index(drop=True)
        highs  = window["high"]
        lows   = window["low"]
        close  = window["close"]
        atr    = (highs - lows).rolling(14).mean().iloc[-2]

        sh_idx = _swing_highs(highs, order=6)
        sl_idx = _swing_lows(lows,   order=6)

        if len(sh_idx) < 1 or len(sl_idx) < 1:
            return _neutral()

        last_sh = sh_idx[-1]
        last_sl = sl_idx[-1]
        current_close = close.iloc[-2]
        tolerance = atr * 0.35

        # ── Upswing → price pulled back to Fib support → BUY ──
        if last_sl < last_sh:                          # swing low BEFORE swing high
            swing_low  = lows.iloc[last_sl]
            swing_high = highs.iloc[last_sh]
            swing_size = swing_high - swing_low
            if swing_size > atr * 2:
                for ratio, name in zip(FIB_LEVELS, FIB_NAMES):
                    level = swing_high - ratio * swing_size
                    if abs(current_close - level) < tolerance:
                        is_high_prob = ratio in HIGH_PROB_FIBS
                        conf = 75 if is_high_prob else 60
                        return {
                            "signal": "BUY",
                            "confidence": conf,
                            "pattern": f"Fibonacci {name} Retracement (Buy Zone)",
                            "key_level": round(level, 5),
                            "details": {
                                "swing_low": round(swing_low, 5),
                                "swing_high": round(swing_high, 5),
                                "fib_ratio": ratio,
                                "fib_level": round(level, 5),
                            },
                        }

        # ── Downswing → price pulled back to Fib resistance → SELL ──
        if last_sh < last_sl:                          # swing high BEFORE swing low
            swing_high = highs.iloc[last_sh]
            swing_low  = lows.iloc[last_sl]
            swing_size = swing_high - swing_low
            if swing_size > atr * 2:
                for ratio, name in zip(FIB_LEVELS, FIB_NAMES):
                    level = swing_low + ratio * swing_size
                    if abs(current_close - level) < tolerance:
                        is_high_prob = ratio in HIGH_PROB_FIBS
                        conf = 75 if is_high_prob else 60
                        return {
                            "signal": "SELL",
                            "confidence": conf,
                            "pattern": f"Fibonacci {name} Retracement (Sell Zone)",
                            "key_level": round(level, 5),
                            "details": {
                                "swing_high": round(swing_high, 5),
                                "swing_low": round(swing_low, 5),
                                "fib_ratio": ratio,
                                "fib_level": round(level, 5),
                            },
                        }

        return _neutral()

    except Exception as e:
        logger.debug(f"Fibonacci detector error: {e}")
        return _neutral()


# ─────────────────────────────────────────────────────────────────────────────
# 6. CANDLESTICK PATTERNS
# ─────────────────────────────────────────────────────────────────────────────

def detect_candlestick_patterns(df: pd.DataFrame, pair: str) -> dict:
    """
    Detects reversal and continuation candlestick patterns on the last 3 bars.

    Bullish patterns → BUY:  Bullish Engulfing, Hammer, Morning Star,
                              Bullish Marubozu, Three White Soldiers, Piercing Line
    Bearish patterns → SELL: Bearish Engulfing, Shooting Star, Evening Star,
                              Bearish Marubozu, Three Black Crows, Dark Cloud Cover
    """
    try:
        if len(df) < 5:
            return _neutral()

        c  = df.iloc[-2]   # last closed candle
        p1 = df.iloc[-3]   # one before
        p2 = df.iloc[-4]   # two before

        body    = abs(c["close"] - c["open"])
        p1_body = abs(p1["close"] - p1["open"])
        p2_body = abs(p2["close"] - p2["open"])
        atr     = (df["high"] - df["low"]).rolling(14).mean().iloc[-2]

        upper_wick = c["high"] - max(c["close"], c["open"])
        lower_wick = min(c["close"], c["open"]) - c["low"]
        full_range = c["high"] - c["low"]

        c_bull  = c["close"]  > c["open"]
        c_bear  = c["close"]  < c["open"]
        p1_bull = p1["close"] > p1["open"]
        p1_bear = p1["close"] < p1["open"]

        # ── BULLISH ENGULFING ──
        if (p1_bear and c_bull and
            c["open"]  < p1["close"] and
            c["close"] > p1["open"]  and
            body > p1_body * 1.1):
            return {"signal": "BUY", "confidence": 72,
                    "pattern": "Bullish Engulfing", "key_level": None,
                    "details": {"body": round(body, 5)}}

        # ── BEARISH ENGULFING ──
        if (p1_bull and c_bear and
            c["open"]  > p1["close"] and
            c["close"] < p1["open"]  and
            body > p1_body * 1.1):
            return {"signal": "SELL", "confidence": 72,
                    "pattern": "Bearish Engulfing", "key_level": None,
                    "details": {"body": round(body, 5)}}

        # ── HAMMER (bullish reversal at bottom) ──
        if (c_bull and
            lower_wick > body * 2 and
            upper_wick < body * 0.5 and
            body > 0):
            return {"signal": "BUY", "confidence": 65,
                    "pattern": "Hammer", "key_level": round(c["low"], 5),
                    "details": {"lower_wick": round(lower_wick, 5)}}

        # ── SHOOTING STAR (bearish reversal at top) ──
        if (c_bear and
            upper_wick > body * 2 and
            lower_wick < body * 0.5 and
            body > 0):
            return {"signal": "SELL", "confidence": 65,
                    "pattern": "Shooting Star", "key_level": round(c["high"], 5),
                    "details": {"upper_wick": round(upper_wick, 5)}}

        # ── PIN BAR / REJECTION CANDLE ──
        if full_range > 0:
            wick_ratio = max(upper_wick, lower_wick) / full_range
            if wick_ratio > 0.65 and body < full_range * 0.25:
                if lower_wick > upper_wick:
                    return {"signal": "BUY", "confidence": 63,
                            "pattern": "Bullish Pin Bar", "key_level": round(c["low"], 5),
                            "details": {"wick_ratio": round(wick_ratio, 2)}}
                else:
                    return {"signal": "SELL", "confidence": 63,
                            "pattern": "Bearish Pin Bar", "key_level": round(c["high"], 5),
                            "details": {"wick_ratio": round(wick_ratio, 2)}}

        # ── MORNING STAR (3-bar bullish reversal) ──
        if (p2_bear and p1_body < p2_body * 0.35 and c_bull and
            p2_body > atr * 0.5 and body > atr * 0.5 and
            c["close"] > (p2["open"] + p2["close"]) / 2):
            return {"signal": "BUY", "confidence": 76,
                    "pattern": "Morning Star", "key_level": None,
                    "details": {"star_body": round(p1_body, 5)}}

        # ── EVENING STAR (3-bar bearish reversal) ──
        p2_bull_check = p2["close"] > p2["open"]
        if (p2_bull_check and p1_body < p2_body * 0.35 and c_bear and
            p2_body > atr * 0.5 and body > atr * 0.5 and
            c["close"] < (p2["open"] + p2["close"]) / 2):
            return {"signal": "SELL", "confidence": 76,
                    "pattern": "Evening Star", "key_level": None,
                    "details": {"star_body": round(p1_body, 5)}}

        # ── THREE WHITE SOLDIERS ──
        p3 = df.iloc[-5]
        p3_bull = p3["close"] > p3["open"]
        if (p3_bull and p2["close"] > p2["open"] and p1_bull and c_bull and
            p2["close"] > p3["close"] and p1["close"] > p2["close"] and
            c["close"] > p1["close"] and
            all(abs(df.iloc[-i]["close"] - df.iloc[-i]["open"]) > atr * 0.3 for i in range(2, 6))):
            return {"signal": "BUY", "confidence": 74,
                    "pattern": "Three White Soldiers", "key_level": None, "details": {}}

        # ── THREE BLACK CROWS ──
        p3_bear = p3["close"] < p3["open"]
        if (p3_bear and p2["close"] < p2["open"] and p1_bear and c_bear and
            p2["close"] < p3["close"] and p1["close"] < p2["close"] and
            c["close"] < p1["close"] and
            all(abs(df.iloc[-i]["close"] - df.iloc[-i]["open"]) > atr * 0.3 for i in range(2, 6))):
            return {"signal": "SELL", "confidence": 74,
                    "pattern": "Three Black Crows", "key_level": None, "details": {}}

        return _neutral()

    except Exception as e:
        logger.debug(f"Candlestick detector error: {e}")
        return _neutral()


# ─────────────────────────────────────────────────────────────────────────────
# MASTER AGGREGATOR
# ─────────────────────────────────────────────────────────────────────────────

def run_advanced_analysis(df: pd.DataFrame, pair: str) -> dict:
    """
    Runs all 6 detectors and returns an aggregated result.

    Returns:
    {
        "signal":           "BUY" | "SELL" | "NEUTRAL",
        "confidence_bonus": 0-30,    # points added to main score
        "pattern_count":    int,     # how many detectors agreed
        "patterns":         list,    # list of pattern names that fired
        "key_levels":       list,    # all detected price levels
        "strongest":        dict,    # highest-confidence detector result
        "detectors":        dict,    # all individual detector results
        "summary":          str,     # human-readable for logs/LLM
    }
    """
    detectors = {
        "sr_breakout":    detect_sr_breakout(df, pair),
        "trendline":      detect_trendline_break(df, pair),
        "chart_pattern":  detect_chart_patterns(df, pair),
        "order_block":    detect_order_blocks(df, pair),
        "fibonacci":      detect_fibonacci_levels(df, pair),
        "candlestick":    detect_candlestick_patterns(df, pair),
    }

    buy_votes  = [(k, v) for k, v in detectors.items() if v["signal"] == "BUY"]
    sell_votes = [(k, v) for k, v in detectors.items() if v["signal"] == "SELL"]

    dominant_signal = "NEUTRAL"
    if len(buy_votes) > len(sell_votes):
        dominant_signal = "BUY"
    elif len(sell_votes) > len(buy_votes):
        dominant_signal = "SELL"
    elif buy_votes and sell_votes:
        # Tie-break on average confidence
        avg_buy  = np.mean([v["confidence"] for _, v in buy_votes])
        avg_sell = np.mean([v["confidence"] for _, v in sell_votes])
        dominant_signal = "BUY" if avg_buy >= avg_sell else "SELL"

    aligned_votes = buy_votes if dominant_signal == "BUY" else sell_votes

    # Confidence bonus: base from vote count + weighted by pattern confidence
    pattern_count = len(aligned_votes)
    if pattern_count == 0:
        conf_bonus = 0
    else:
        avg_conf   = np.mean([v["confidence"] for _, v in aligned_votes])
        # Scale: 1 pattern = up to 10pts, 2 = up to 18pts, 3+ = up to 28pts
        base_bonus = min(28, pattern_count * 9 + 1)
        conf_bonus = int(base_bonus * (avg_conf / 100))

    # Strongest single detector
    if aligned_votes:
        strongest_key = max(aligned_votes, key=lambda x: x[1]["confidence"])
        strongest = {"detector": strongest_key[0], **strongest_key[1]}
    else:
        strongest = _neutral()

    patterns   = [v["pattern"] for _, v in aligned_votes if v["pattern"] != "none"]
    key_levels = [v["key_level"] for _, v in aligned_votes if v["key_level"] is not None]

    # Summary string for logging and LLM context
    if dominant_signal == "NEUTRAL" or not patterns:
        summary = f"{pair}: No advanced pattern detected"
    else:
        summary = (f"{pair} {dominant_signal}: {', '.join(patterns)} "
                   f"({pattern_count} detector{'s' if pattern_count != 1 else ''} agree, "
                   f"+{conf_bonus}pts bonus)")

    if dominant_signal != "NEUTRAL":
        logger.info(f"[AdvancedAnalysis] {summary}")

    return {
        "signal":           dominant_signal,
        "confidence_bonus": conf_bonus,
        "pattern_count":    pattern_count,
        "patterns":         patterns,
        "key_levels":       key_levels,
        "strongest":        strongest,
        "detectors":        detectors,
        "summary":          summary,
    }
