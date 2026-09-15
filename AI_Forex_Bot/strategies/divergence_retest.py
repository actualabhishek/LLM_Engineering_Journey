"""
strategies/divergence_retest.py
--------------------------------
RSI-divergence + retest confirmation — migrated out of the previously
orphaned strategies/signal_engine_v2.py (built, never wired into the live
pipeline). signal_engine_v2.py fired trades on divergence alone; that raw
form is dropped here in favor of a two-step version: detect the divergence
(a LEADING signal — it fires before price actually reverses), then require
a retest/rejection candle (pin bar or engulfing) at the divergence level
before treating it as tradeable. That confirmation step is what makes it
safe to add as a 7th trigger alongside signal_engine.py's structural
triggers without introducing a second raw, noise-prone "fire on divergence
alone" signal.

Exposes two composable functions, used by
strategies/signal_engine.py::trigger_divergence_retest():
  detect_rsi_divergence(df, pair) -> direction / level / strength / rsi
  confirm_retest(df, pair, level, direction) -> confirmed / entry_price / detail
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, List, Optional


def _pip_size(pair: str) -> float:
    return 0.01 if ("JPY" in pair.upper() or "XAU" in pair.upper()) else 0.0001


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _swing_highs(df: pd.DataFrame, lookback: int = 5) -> List[int]:
    highs = []
    for i in range(lookback, len(df) - lookback):
        if df["high"].iloc[i] == df["high"].iloc[i - lookback:i + lookback + 1].max():
            highs.append(i)
    return highs


def _swing_lows(df: pd.DataFrame, lookback: int = 5) -> List[int]:
    lows = []
    for i in range(lookback, len(df) - lookback):
        if df["low"].iloc[i] == df["low"].iloc[i - lookback:i + lookback + 1].min():
            lows.append(i)
    return lows


_NEUTRAL_DIVERGENCE = {"direction": "NEUTRAL", "level": None, "strength": 0, "rsi": None}


def detect_rsi_divergence(df: pd.DataFrame, pair: str, lookback: int = 30) -> Dict:
    """
    Detect RSI divergence over the most recent `lookback` bars.

    Bullish divergence: price makes a lower low while RSI makes a higher low
    -> selling pressure is exhausting, a reversal up is favored.
    Bearish divergence: price makes a higher high while RSI makes a lower high
    -> buying pressure is exhausting, a reversal down is favored.

    Returns {"direction": "BUY"/"SELL"/"NEUTRAL", "level": float|None,
             "strength": int 0-2, "rsi": float|None}.
    `level` is the price of the divergence swing point — the level
    confirm_retest() should watch for a pullback/rejection at.
    """
    if df is None or len(df) < 50:
        return _NEUTRAL_DIVERGENCE

    rsi_vals = _rsi(df["close"])
    df_recent = df.iloc[-lookback:]
    rsi_recent = rsi_vals.iloc[-lookback:]
    if rsi_recent.empty or pd.isna(rsi_recent.iloc[-1]):
        return _NEUTRAL_DIVERGENCE
    current_rsi = rsi_recent.iloc[-1]

    # Bullish divergence: price LL, RSI HL
    price_lows = _swing_lows(df_recent, lookback=4)
    if len(price_lows) >= 2:
        i1, i2 = price_lows[-2], price_lows[-1]
        price_ll = df_recent["low"].iloc[i2] < df_recent["low"].iloc[i1]
        rsi_hl = rsi_recent.iloc[i2] > rsi_recent.iloc[i1]
        if price_ll and rsi_hl and current_rsi < 45:
            strength = 0
            if current_rsi < 35:
                strength += 1
            if rsi_recent.iloc[i2] - rsi_recent.iloc[i1] > 5:
                strength += 1
            return {
                "direction": "BUY",
                "level": round(df_recent["low"].iloc[i2], 5),
                "strength": strength,
                "rsi": round(current_rsi, 1),
            }

    # Bearish divergence: price HH, RSI LH
    price_highs = _swing_highs(df_recent, lookback=4)
    if len(price_highs) >= 2:
        i1, i2 = price_highs[-2], price_highs[-1]
        price_hh = df_recent["high"].iloc[i2] > df_recent["high"].iloc[i1]
        rsi_lh = rsi_recent.iloc[i2] < rsi_recent.iloc[i1]
        if price_hh and rsi_lh and current_rsi > 55:
            strength = 0
            if current_rsi > 65:
                strength += 1
            if rsi_recent.iloc[i1] - rsi_recent.iloc[i2] > 5:
                strength += 1
            return {
                "direction": "SELL",
                "level": round(df_recent["high"].iloc[i2], 5),
                "strength": strength,
                "rsi": round(current_rsi, 1),
            }

    return _NEUTRAL_DIVERGENCE


_NO_RETEST = {"confirmed": False, "entry_price": 0.0, "detail": ""}


def confirm_retest(df: pd.DataFrame, pair: str, level: Optional[float], direction: str) -> Dict:
    """
    Check whether the most recently closed bar shows a retest/rejection of
    `level` in `direction` — a pin bar or engulfing candle within striking
    distance of the level. This is the confirmation gate: a bare divergence
    reading is not enough to trade — price must actually come back and
    reject the level first.

    Returns {"confirmed": bool, "entry_price": float, "detail": str}.
    """
    if df is None or len(df) < 5 or level is None:
        return _NO_RETEST

    atr_val = _atr(df).iloc[-2]
    if not atr_val or pd.isna(atr_val):
        return _NO_RETEST

    c = df.iloc[-2]  # last CLOSED bar
    p = df.iloc[-3]
    body = abs(c["close"] - c["open"])
    candle = c["high"] - c["low"]
    if candle < atr_val * 0.2:
        return _NO_RETEST

    upper_wick = c["high"] - max(c["close"], c["open"])
    lower_wick = min(c["close"], c["open"]) - c["low"]
    near_level = atr_val * 0.8  # within 0.8 ATR of the divergence level

    if direction == "BUY":
        if abs(c["low"] - level) > near_level and abs(c["close"] - level) > near_level:
            return _NO_RETEST
        pin_bar = lower_wick > candle * 0.55 and body < candle * 0.35
        engulf = (c["close"] > c["open"] and p["close"] < p["open"]
                  and c["close"] > p["open"] and c["open"] < p["close"])
        if pin_bar or engulf:
            return {
                "confirmed": True,
                "entry_price": round(c["close"], 5),
                "detail": f"{'pin-bar' if pin_bar else 'engulfing'} retest of {level:.5f}",
            }
    else:  # SELL
        if abs(c["high"] - level) > near_level and abs(c["close"] - level) > near_level:
            return _NO_RETEST
        pin_bar = upper_wick > candle * 0.55 and body < candle * 0.35
        engulf = (c["close"] < c["open"] and p["close"] > p["open"]
                  and c["close"] < p["open"] and c["open"] > p["close"])
        if pin_bar or engulf:
            return {
                "confirmed": True,
                "entry_price": round(c["close"], 5),
                "detail": f"{'pin-bar' if pin_bar else 'engulfing'} retest of {level:.5f}",
            }

    return _NO_RETEST
