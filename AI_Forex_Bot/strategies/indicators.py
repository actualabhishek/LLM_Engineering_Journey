"""
strategies/indicators.py
------------------------
Pure deterministic indicator calculations.
Uses pandas-ta for efficiency.
No LLM dependency — this is the algorithmic backbone.

Indicators included:
  EMA (9, 21, 50, 200)
  RSI (14)
  MACD (12/26/9)
  ATR (14)
  ADX (14)
  Bollinger Bands (20/2)
  Supertrend (10/3)
  Momentum score (composite)
"""

from typing import Dict, Optional
import pandas as pd
import pandas_ta as ta
import numpy as np

from core.config_manager import config
from core.logger import get_logger

logger = get_logger(__name__)

# Pip value per pair (for spread/SL calculation normalization)
PIP_VALUES = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
    "USDCAD": 0.0001, "EURJPY": 0.01, "GBPJPY": 0.01, "USDJPY": 0.01,
    "XAUUSD": 0.01,  # gold quotes to 2 decimals (e.g. 4348.23) — not a forex pair pip convention
}


def get_pip_value(pair: str) -> float:
    return PIP_VALUES.get(pair, 0.0001)


def calculate_indicators(df: pd.DataFrame, pair: str) -> Optional[Dict]:
    """
    Calculate all indicators on OHLCV dataframe.
    Expects columns: open, high, low, close, volume
    Returns dict of indicator values for the LAST completed candle.
    Returns None if insufficient data.

    Decision logic:
      - This is PURE algorithmic logic. No LLM needed here.
      - LLM is only used AFTER this to interpret confluence.
    """
    cfg = config.get("indicators")

    if df is None or len(df) < 210:
        logger.warning(f"{pair}: Insufficient candle data ({len(df) if df is not None else 0} bars)")
        return None

    try:
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]

        # ---- EMAs ----
        df["ema9"]   = ta.ema(df["close"], length=cfg["ema"]["fast"])
        df["ema21"]  = ta.ema(df["close"], length=cfg["ema"]["medium"])
        df["ema50"]  = ta.ema(df["close"], length=cfg["ema"]["slow"])
        df["ema200"] = ta.ema(df["close"], length=cfg["ema"]["trend_200"])

        # ---- RSI ----
        df["rsi"] = ta.rsi(df["close"], length=cfg["rsi"]["period"])

        # ---- MACD ----
        macd_df = ta.macd(df["close"],
                          fast=cfg["macd"]["fast"],
                          slow=cfg["macd"]["slow"],
                          signal=cfg["macd"]["signal"])
        df["macd"]        = macd_df.iloc[:, 0]
        df["macd_signal"] = macd_df.iloc[:, 2]
        df["macd_hist"]   = macd_df.iloc[:, 1]

        # ---- ATR ----
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=cfg["atr"]["period"])

        # ---- ADX ----
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=cfg["adx"]["period"])
        df["adx"]    = adx_df.iloc[:, 0]
        df["dmi_pos"] = adx_df.iloc[:, 1]
        df["dmi_neg"] = adx_df.iloc[:, 2]

        # ---- Bollinger Bands ----
        bb_df = ta.bbands(df["close"],
                          length=cfg["bollinger"]["period"],
                          std=cfg["bollinger"]["std_dev"])
        df["bb_upper"]  = bb_df.iloc[:, 0]
        df["bb_middle"] = bb_df.iloc[:, 1]
        df["bb_lower"]  = bb_df.iloc[:, 2]
        df["bb_width"]  = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]

        # ---- Supertrend ----
        st_df = ta.supertrend(df["high"], df["low"], df["close"],
                              length=cfg["supertrend"]["period"],
                              multiplier=cfg["supertrend"]["multiplier"])
        df["supertrend"]       = st_df.iloc[:, 0]
        df["supertrend_dir"]   = st_df.iloc[:, 1]  # 1 = bullish, -1 = bearish

        # ---- Get last complete candle (index -2 = last closed bar) ----
        row = df.iloc[-2]
        prev_row = df.iloc[-3]
        pip = get_pip_value(pair)

        # ---- Trend bias assessments ----
        # Price vs EMA structure
        price = row["close"]
        ema_bullish = price > row["ema9"] > row["ema21"] > row["ema50"]
        ema_bearish = price < row["ema9"] < row["ema21"] < row["ema50"]
        long_trend_bull = price > row["ema200"]
        long_trend_bear = price < row["ema200"]

        # MACD bias
        macd_bull = row["macd"] > row["macd_signal"] and row["macd_hist"] > 0
        macd_bear = row["macd"] < row["macd_signal"] and row["macd_hist"] < 0
        macd_cross_bull = prev_row["macd_hist"] < 0 < row["macd_hist"]
        macd_cross_bear = prev_row["macd_hist"] > 0 > row["macd_hist"]

        # RSI
        rsi_val = row["rsi"]
        rsi_bull = cfg["rsi"]["neutral_low"] < rsi_val < cfg["rsi"]["overbought"]
        rsi_bear = cfg["rsi"]["oversold"] < rsi_val < cfg["rsi"]["neutral_high"]
        rsi_overbought = rsi_val >= cfg["rsi"]["overbought"]
        rsi_oversold   = rsi_val <= cfg["rsi"]["oversold"]

        # ADX strength
        adx_val = row["adx"]
        trending  = adx_val >= cfg["adx"]["trending_threshold"]
        strong_trend = adx_val >= cfg["adx"]["strong_trend"]

        # Supertrend
        st_bull = row["supertrend_dir"] == 1
        st_bear = row["supertrend_dir"] == -1

        # ATR-based volatility check
        atr_pips = row["atr"] / pip
        vol_ok = cfg["atr"]["volatility_min_pips"] <= atr_pips <= cfg["atr"]["volatility_max_pips"]

        # Bollinger band squeeze detection
        recent_bb_width = df["bb_width"].iloc[-20:]
        bb_squeeze = row["bb_width"] < recent_bb_width.quantile(0.2)

        # Price position within BB
        bb_position = (price - row["bb_lower"]) / (row["bb_upper"] - row["bb_lower"])

        # Momentum scoring (composite 0-100)
        momentum_score = _calc_momentum_score(
            ema_bullish=ema_bullish,
            ema_bearish=ema_bearish,
            macd_bull=macd_bull,
            macd_bear=macd_bear,
            st_bull=st_bull,
            st_bear=st_bear,
            rsi_bull=rsi_bull,
            rsi_bear=rsi_bear,
            adx=adx_val,
            dmi_pos=row["dmi_pos"],
            dmi_neg=row["dmi_neg"],
        )

        # Trend direction assessment
        if ema_bullish and st_bull and long_trend_bull:
            trend_direction = "BUY"
        elif ema_bearish and st_bear and long_trend_bear:
            trend_direction = "SELL"
        elif ema_bullish and st_bull:
            trend_direction = "BUY_WEAK"
        elif ema_bearish and st_bear:
            trend_direction = "SELL_WEAK"
        else:
            trend_direction = "NEUTRAL"

        # ATR-based SL/TP distances
        sl_distance_pips = row["atr"] * config.get("risk", "atr_sl_multiplier") / pip
        tp_distance_pips = sl_distance_pips * config.get("risk", "atr_tp_multiplier") / config.get("risk", "atr_sl_multiplier")

        return {
            # Price
            "price": round(price, 5),
            "pair": pair,
            # EMA
            "ema9":   round(row["ema9"], 5),
            "ema21":  round(row["ema21"], 5),
            "ema50":  round(row["ema50"], 5),
            "ema200": round(row["ema200"], 5),
            "ema_bullish": ema_bullish,
            "ema_bearish": ema_bearish,
            "long_trend_bull": long_trend_bull,
            "long_trend_bear": long_trend_bear,
            # RSI
            "rsi": round(rsi_val, 1),
            "rsi_overbought": rsi_overbought,
            "rsi_oversold": rsi_oversold,
            "rsi_bull": rsi_bull,
            "rsi_bear": rsi_bear,
            # MACD
            "macd": round(row["macd"], 6),
            "macd_signal": round(row["macd_signal"], 6),
            "macd_hist": round(row["macd_hist"], 6),
            "macd_bull": macd_bull,
            "macd_bear": macd_bear,
            "macd_cross_bull": macd_cross_bull,
            "macd_cross_bear": macd_cross_bear,
            # ADX
            "adx": round(adx_val, 1),
            "dmi_pos": round(row["dmi_pos"], 1),
            "dmi_neg": round(row["dmi_neg"], 1),
            "trending": trending,
            "strong_trend": strong_trend,
            # ATR / Volatility
            "atr": round(row["atr"], 5),
            "atr_pips": round(atr_pips, 1),
            "volatility_ok": vol_ok,
            # Bollinger
            "bb_upper":  round(row["bb_upper"], 5),
            "bb_lower":  round(row["bb_lower"], 5),
            "bb_width":  round(row["bb_width"], 4),
            "bb_squeeze": bb_squeeze,
            "bb_position": round(bb_position, 2),
            # Supertrend
            "supertrend": round(row["supertrend"], 5),
            "supertrend_bull": st_bull,
            "supertrend_bear": st_bear,
            # Composite
            "trend_direction": trend_direction,
            "momentum_score": momentum_score,
            # Trade sizing
            "sl_distance_pips": round(sl_distance_pips, 1),
            "tp_distance_pips": round(tp_distance_pips, 1),
        }

    except Exception as e:
        logger.error(f"Indicator calculation failed for {pair}: {e}", exc_info=True)
        return None


def _calc_momentum_score(
    ema_bullish: bool, ema_bearish: bool,
    macd_bull: bool, macd_bear: bool,
    st_bull: bool, st_bear: bool,
    rsi_bull: bool, rsi_bear: bool,
    adx: float, dmi_pos: float, dmi_neg: float,
) -> float:
    """
    Composite momentum score 0-100.
    > 60 = bullish momentum
    < 40 = bearish momentum
    40-60 = neutral/mixed
    """
    score = 50.0  # Start neutral

    # EMA stack (strong weight: 20pts)
    if ema_bullish:   score += 20
    elif ema_bearish: score -= 20

    # MACD (12pts)
    if macd_bull:   score += 12
    elif macd_bear: score -= 12

    # Supertrend (10pts)
    if st_bull:   score += 10
    elif st_bear: score -= 10

    # RSI (8pts)
    if rsi_bull:   score += 8
    elif rsi_bear: score -= 8

    # ADX strength boost (if trending, amplify direction by up to 10pts)
    if adx >= 25:
        direction_boost = min((adx - 25) / 40 * 10, 10)
        if dmi_pos > dmi_neg:
            score += direction_boost
        elif dmi_neg > dmi_pos:
            score -= direction_boost

    return round(max(0.0, min(100.0, score)), 1)


def detect_market_structure(df: pd.DataFrame, lookback: int = 20) -> Dict:
    """
    Detect basic market structure: HH/HL (uptrend), LH/LL (downtrend).
    Uses swing highs/lows from recent candles.
    Pure algorithmic, no LLM needed.
    """
    if df is None or len(df) < lookback + 2:
        return {"structure": "UNKNOWN", "swing_high": None, "swing_low": None}

    try:
        recent = df.iloc[-(lookback + 2):-1]
        highs = recent["high"].values
        lows  = recent["low"].values

        # Find swing highs (local maxima)
        swing_highs = [highs[i] for i in range(1, len(highs) - 1)
                       if highs[i] > highs[i-1] and highs[i] > highs[i+1]]
        # Find swing lows (local minima)
        swing_lows  = [lows[i] for i in range(1, len(lows) - 1)
                       if lows[i] < lows[i-1] and lows[i] < lows[i+1]]

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs[-1] > swing_highs[-2]  # Higher high
            hl = swing_lows[-1]  > swing_lows[-2]   # Higher low
            lh = swing_highs[-1] < swing_highs[-2]  # Lower high
            ll = swing_lows[-1]  < swing_lows[-2]   # Lower low

            if hh and hl:
                structure = "UPTREND"
            elif lh and ll:
                structure = "DOWNTREND"
            elif hh and ll:
                structure = "EXPANDING"
            else:
                structure = "RANGING"
        else:
            structure = "INSUFFICIENT_DATA"

        return {
            "structure": structure,
            "swing_high": round(swing_highs[-1], 5) if swing_highs else None,
            "swing_low":  round(swing_lows[-1], 5)  if swing_lows else None,
        }
    except Exception:
        return {"structure": "UNKNOWN", "swing_high": None, "swing_low": None}
