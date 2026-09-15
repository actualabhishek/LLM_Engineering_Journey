"""
early_entry.py
--------------
Early entry detection system — catches trades BEFORE lagging indicators
fully confirm, using 5 leading/anticipatory signals:

  1. EMA Cross Anticipation   — EMA9 approaching EMA21 cross (1-2 bars before)
  2. Candle Close Confirmation — wait for M15 candle to FULLY close before entry
  3. H1 Momentum Pre-signal   — H1 shows momentum building before M15 confirms
  4. Order Flow Imbalance     — aggressive buying/selling in last 3 bars
  5. Micro Structure Break    — price breaks last swing high/low on M15

Each detector returns an entry_quality score (0-100) and an
optimal_entry_price (often better than current market price).

The master function run_early_entry_analysis() returns:
  - entry_quality:     0-100 (how good the entry timing is)
  - optimal_entry:     float (best price to enter at)
  - entry_type:        "IMMEDIATE" | "LIMIT" | "WAIT"
  - confidence_bonus:  0-25 pts added to main score
  - reason:            human-readable explanation
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional
from core.logger import get_logger

logger = get_logger(__name__)

def _pip(pair: str) -> float:
    """Return pip size for a currency pair."""
    return 0.01 if ("JPY" in pair.upper() or "XAU" in pair.upper()) else 0.0001



# ─────────────────────────────────────────────────────────────────────────────
# 1. EMA CROSS ANTICIPATION
# ─────────────────────────────────────────────────────────────────────────────

def detect_ema_cross_anticipation(df: pd.DataFrame, direction: str) -> dict:
    """
    Detects when EMA9 is within 30% of crossing EMA21 — the setup is
    forming but hasn't fired yet. This is 1-3 bars BEFORE the main
    indicator signal triggers, giving a much better entry price.

    Also detects EMA9/21 cross that just happened (last 1-2 bars) —
    these are fresh crosses worth entering before price runs away.

    Returns quality 0-100 and how many pips earlier than normal entry.
    """
    try:
        import pandas_ta as ta
        if len(df) < 30:
            return {"quality": 0, "type": "none", "pips_saved": 0}

        ema9  = ta.ema(df["close"], length=9)
        ema21 = ta.ema(df["close"], length=21)
        atr   = ta.atr(df["high"], df["low"], df["close"], length=14)
        pip   = 0.0001  # JPY pairs handled by caller via pair param

        if ema9.isna().any() or ema21.isna().any():
            return {"quality": 0, "type": "none", "pips_saved": 0}

        gap_now  = ema9.iloc[-2] - ema21.iloc[-2]   # current gap
        gap_prev = ema9.iloc[-3] - ema21.iloc[-3]   # previous gap
        gap_prev2= ema9.iloc[-4] - ema21.iloc[-4]   # 2 bars ago
        atr_now  = atr.iloc[-2]

        # Fresh cross: EMA9 crossed EMA21 in last 1-2 bars
        just_crossed_bull = gap_prev <= 0 and gap_now > 0
        just_crossed_bear = gap_prev >= 0 and gap_now < 0

        # Approaching cross: gap is converging and within 30% of ATR
        approaching_bull = (gap_prev2 < gap_prev < gap_now < 0 and
                           abs(gap_now) < atr_now * 0.3)
        approaching_bear = (gap_prev2 > gap_prev > gap_now > 0 and
                           abs(gap_now) < atr_now * 0.3)

        # Accelerating convergence (momentum in cross direction)
        conv_speed = abs(gap_now - gap_prev) / (atr_now + 1e-10)

        if direction == "BUY":
            if just_crossed_bull:
                quality = 85
                entry_type = "FRESH_CROSS"
                pips_saved = 3
            elif approaching_bull:
                quality = 75
                entry_type = "PRE_CROSS"
                pips_saved = 6
            else:
                quality = 30
                entry_type = "none"
                pips_saved = 0
        else:  # SELL
            if just_crossed_bear:
                quality = 85
                entry_type = "FRESH_CROSS"
                pips_saved = 3
            elif approaching_bear:
                quality = 75
                entry_type = "PRE_CROSS"
                pips_saved = 6
            else:
                quality = 30
                entry_type = "none"
                pips_saved = 0

        return {
            "quality":    quality,
            "type":       entry_type,
            "pips_saved": pips_saved,
            "gap_now":    round(gap_now, 6),
            "just_crossed": just_crossed_bull or just_crossed_bear,
        }

    except Exception as e:
        logger.debug(f"EMA cross anticipation error: {e}")
        return {"quality": 0, "type": "none", "pips_saved": 0}


# ─────────────────────────────────────────────────────────────────────────────
# 2. CANDLE CLOSE CONFIRMATION
# ─────────────────────────────────────────────────────────────────────────────

def check_candle_close_quality(df: pd.DataFrame, direction: str) -> dict:
    """
    Evaluates the quality of the last CLOSED candle as an entry signal.
    Strong candles (large body, small wicks, closed in direction) give
    high quality. Doji or spinning tops suggest hesitation — wait.

    Also checks if we're entering at the open of a new candle (best)
    vs mid-candle (worst — price already moved).

    Returns quality 0-100 and whether to enter immediately or wait.
    """
    try:
        if len(df) < 5:
            return {"quality": 50, "enter_now": True, "reason": "insufficient data"}

        c = df.iloc[-2]   # last CLOSED candle
        body   = abs(c["close"] - c["open"])
        full   = c["high"] - c["low"]
        upper_wick = c["high"] - max(c["close"], c["open"])
        lower_wick = min(c["close"], c["open"]) - c["low"]
        atr    = (df["high"] - df["low"]).rolling(14).mean().iloc[-2]

        if full == 0:
            return {"quality": 50, "enter_now": True, "reason": "zero range candle"}

        body_pct = body / full
        is_bull  = c["close"] > c["open"]
        is_bear  = c["close"] < c["open"]

        if direction == "BUY":
            # Strong bullish close: large body, closed near high, small upper wick
            if is_bull and body_pct >= 0.7 and upper_wick < body * 0.3:
                quality = 90
                reason  = f"Strong bull close — {body_pct:.0%} body, closed near high"
            elif is_bull and body_pct >= 0.5:
                quality = 75
                reason  = f"Decent bull close — {body_pct:.0%} body"
            elif is_bull and body_pct >= 0.3:
                quality = 60
                reason  = "Weak bull close — acceptable"
            elif body_pct < 0.2:
                quality = 25
                reason  = "Doji/indecision candle — consider waiting"
            else:
                quality = 40
                reason  = "Bear candle in buy direction — marginal"

        else:  # SELL
            if is_bear and body_pct >= 0.7 and lower_wick < body * 0.3:
                quality = 90
                reason  = f"Strong bear close — {body_pct:.0%} body, closed near low"
            elif is_bear and body_pct >= 0.5:
                quality = 75
                reason  = f"Decent bear close — {body_pct:.0%} body"
            elif is_bear and body_pct >= 0.3:
                quality = 60
                reason  = "Weak bear close — acceptable"
            elif body_pct < 0.2:
                quality = 25
                reason  = "Doji/indecision candle — consider waiting"
            else:
                quality = 40
                reason  = "Bull candle in sell direction — marginal"

        # Don't block on candle quality alone — just score it
        enter_now = quality >= 40

        return {
            "quality":   quality,
            "enter_now": enter_now,
            "body_pct":  round(body_pct, 2),
            "reason":    reason,
        }

    except Exception as e:
        logger.debug(f"Candle quality check error: {e}")
        return {"quality": 50, "enter_now": True, "reason": "check failed"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. H1 MOMENTUM PRE-SIGNAL
# ─────────────────────────────────────────────────────────────────────────────

def check_h1_momentum(df_h1: Optional[pd.DataFrame], direction: str) -> dict:
    """
    H1 RSI and MACD momentum building before M15 confirms.
    If H1 MACD just crossed bullish and RSI > 50 and trending up,
    the M15 signal is likely to be valid and entry is early/good.

    If H1 is already overbought (RSI > 70), entry is late — skip or tighten.
    """
    try:
        if df_h1 is None or len(df_h1) < 30:
            return {"quality": 50, "signal": "NEUTRAL", "rsi": 50}

        import pandas_ta as ta
        rsi  = ta.rsi(df_h1["close"], length=14)
        macd = ta.macd(df_h1["close"], fast=12, slow=26, signal=9)

        rsi_now  = rsi.iloc[-2]
        rsi_prev = rsi.iloc[-3]

        macd_hist_now  = macd["MACDh_12_26_9"].iloc[-2]
        macd_hist_prev = macd["MACDh_12_26_9"].iloc[-3]
        macd_rising    = macd_hist_now > macd_hist_prev

        if direction == "BUY":
            if rsi_now > 70:
                return {"quality": 20, "signal": "OVERBOUGHT",
                        "rsi": round(rsi_now, 1),
                        "reason": f"H1 RSI overbought ({rsi_now:.0f}) — late entry"}
            elif 50 < rsi_now <= 65 and rsi_prev < rsi_now and macd_rising:
                return {"quality": 90, "signal": "EARLY",
                        "rsi": round(rsi_now, 1),
                        "reason": f"H1 RSI building ({rsi_now:.0f}↑) with rising MACD — early entry"}
            elif rsi_now > 50 and macd_hist_now > 0:
                return {"quality": 70, "signal": "CONFIRMED",
                        "rsi": round(rsi_now, 1),
                        "reason": f"H1 RSI {rsi_now:.0f} bullish, MACD positive"}
            elif 45 < rsi_now <= 50:
                return {"quality": 55, "signal": "NEUTRAL",
                        "rsi": round(rsi_now, 1),
                        "reason": "H1 neutral — marginal conditions"}
            else:
                return {"quality": 30, "signal": "WEAK",
                        "rsi": round(rsi_now, 1),
                        "reason": f"H1 RSI {rsi_now:.0f} weak for BUY"}

        else:  # SELL
            if rsi_now < 30:
                return {"quality": 20, "signal": "OVERSOLD",
                        "rsi": round(rsi_now, 1),
                        "reason": f"H1 RSI oversold ({rsi_now:.0f}) — late entry"}
            elif 35 <= rsi_now < 50 and rsi_prev > rsi_now and not macd_rising:
                return {"quality": 90, "signal": "EARLY",
                        "rsi": round(rsi_now, 1),
                        "reason": f"H1 RSI falling ({rsi_now:.0f}↓) with falling MACD — early entry"}
            elif rsi_now < 50 and macd_hist_now < 0:
                return {"quality": 70, "signal": "CONFIRMED",
                        "rsi": round(rsi_now, 1),
                        "reason": f"H1 RSI {rsi_now:.0f} bearish, MACD negative"}
            elif 50 <= rsi_now < 55:
                return {"quality": 55, "signal": "NEUTRAL",
                        "rsi": round(rsi_now, 1),
                        "reason": "H1 neutral — marginal conditions"}
            else:
                return {"quality": 30, "signal": "WEAK",
                        "rsi": round(rsi_now, 1),
                        "reason": f"H1 RSI {rsi_now:.0f} weak for SELL"}

    except Exception as e:
        logger.debug(f"H1 momentum check error: {e}")
        return {"quality": 50, "signal": "NEUTRAL", "rsi": 50}


# ─────────────────────────────────────────────────────────────────────────────
# 4. ORDER FLOW IMBALANCE
# ─────────────────────────────────────────────────────────────────────────────

def detect_order_flow_imbalance(df: pd.DataFrame, direction: str) -> dict:
    """
    Detects aggressive buying or selling in the last 3 bars using
    candle body direction and volume (tick volume as proxy).

    Bullish imbalance: 2+ of last 3 bars are strong bull candles with
    above-average volume — institutions are accumulating.

    Returns quality 0-100 and estimated pips of early edge.
    """
    try:
        if len(df) < 20:
            return {"quality": 50, "imbalance": 0}

        recent = df.iloc[-4:-1]   # last 3 closed bars
        avg_vol = df["volume"].iloc[-20:-4].mean()
        atr     = (df["high"] - df["low"]).rolling(14).mean().iloc[-2]

        bull_bars  = 0
        bear_bars  = 0
        vol_above  = 0
        body_sizes = []

        for _, bar in recent.iterrows():
            body = bar["close"] - bar["open"]
            body_sizes.append(abs(body))
            if body > 0:
                bull_bars += 1
            elif body < 0:
                bear_bars += 1
            if bar["volume"] > avg_vol * 1.2:
                vol_above += 1

        avg_body = np.mean(body_sizes) if body_sizes else 0

        if direction == "BUY":
            if bull_bars >= 2 and vol_above >= 2 and avg_body > atr * 0.3:
                quality = 85
                reason  = f"Strong bull flow: {bull_bars}/3 bull bars, {vol_above}/3 high-vol"
            elif bull_bars >= 2 and avg_body > atr * 0.2:
                quality = 70
                reason  = f"Moderate bull flow: {bull_bars}/3 bull bars"
            elif bull_bars >= 1:
                quality = 55
                reason  = "Weak bull flow"
            else:
                quality = 30
                reason  = "No bull order flow"
        else:  # SELL
            if bear_bars >= 2 and vol_above >= 2 and avg_body > atr * 0.3:
                quality = 85
                reason  = f"Strong bear flow: {bear_bars}/3 bear bars, {vol_above}/3 high-vol"
            elif bear_bars >= 2 and avg_body > atr * 0.2:
                quality = 70
                reason  = f"Moderate bear flow: {bear_bars}/3 bear bars"
            elif bear_bars >= 1:
                quality = 55
                reason  = "Weak bear flow"
            else:
                quality = 30
                reason  = "No bear order flow"

        return {
            "quality":   quality,
            "imbalance": bull_bars - bear_bars,
            "vol_above": vol_above,
            "reason":    reason,
        }

    except Exception as e:
        logger.debug(f"Order flow error: {e}")
        return {"quality": 50, "imbalance": 0, "reason": "check failed"}


# ─────────────────────────────────────────────────────────────────────────────
# 5. MICRO STRUCTURE BREAK
# ─────────────────────────────────────────────────────────────────────────────

def detect_micro_structure_break(df: pd.DataFrame, direction: str, pair: str) -> dict:
    """
    Detects when price breaks the most recent swing high (BUY) or swing low (SELL)
    on M15. This is a structural confirmation that happens BEFORE the EMA stack
    fully aligns, giving an earlier entry.

    Also detects "equal highs/lows" — price retesting a previous high/low
    which is a key Smart Money entry zone.

    Returns quality, the broken level, and estimated entry advantage in pips.
    """
    try:
        if len(df) < 20:
            return {"quality": 50, "level": None, "pips_early": 0}

        highs   = df["high"]
        lows    = df["low"]
        close   = df["close"]
        atr     = (highs - lows).rolling(14).mean().iloc[-2]
        pip     = 0.01 if ("JPY" in pair.upper() or "XAU" in pair.upper()) else 0.0001

        # Recent swing points (last 15 bars, ignoring last 2)
        window  = df.iloc[-17:-2]
        recent_swing_high = window["high"].max()
        recent_swing_low  = window["low"].min()
        current_close     = close.iloc[-2]
        prev_close        = close.iloc[-3]

        if direction == "BUY":
            # Break above recent swing high = structural BUY confirmation
            if prev_close <= recent_swing_high and current_close > recent_swing_high + atr * 0.1:
                pips_early = abs(current_close - recent_swing_high) / pip
                quality = min(90, 65 + int(pips_early * 2))
                return {
                    "quality":    quality,
                    "level":      round(recent_swing_high, 5),
                    "pips_early": round(pips_early, 1),
                    "type":       "swing_high_break",
                    "reason":     f"Broke swing high {recent_swing_high:.5f} — structural BUY confirmed",
                }
            # Equal highs (liquidity at same level — breakout imminent)
            elif abs(current_close - recent_swing_high) < atr * 0.15:
                return {
                    "quality":  75,
                    "level":    round(recent_swing_high, 5),
                    "pips_early": 4,
                    "type":     "equal_highs",
                    "reason":   f"Testing equal highs {recent_swing_high:.5f} — breakout likely",
                }

        else:  # SELL
            if prev_close >= recent_swing_low and current_close < recent_swing_low - atr * 0.1:
                pips_early = abs(recent_swing_low - current_close) / pip
                quality = min(90, 65 + int(pips_early * 2))
                return {
                    "quality":    quality,
                    "level":      round(recent_swing_low, 5),
                    "pips_early": round(pips_early, 1),
                    "type":       "swing_low_break",
                    "reason":     f"Broke swing low {recent_swing_low:.5f} — structural SELL confirmed",
                }
            elif abs(current_close - recent_swing_low) < atr * 0.15:
                return {
                    "quality":  75,
                    "level":    round(recent_swing_low, 5),
                    "pips_early": 4,
                    "type":     "equal_lows",
                    "reason":   f"Testing equal lows {recent_swing_low:.5f} — breakdown likely",
                }

        return {"quality": 40, "level": None, "pips_early": 0,
                "reason": "No clear structure break"}

    except Exception as e:
        logger.debug(f"Micro structure error: {e}")
        return {"quality": 40, "level": None, "pips_early": 0}


# ─────────────────────────────────────────────────────────────────────────────
# OPTIMAL ENTRY PRICE CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────

def calculate_optimal_entry(
    df: pd.DataFrame,
    direction: str,
    current_price: float,
    pair: str,
    ema_result: dict,
    candle_result: dict,
    h1_result: dict,
    flow_result: dict,
    structure_result: dict,
) -> tuple[float, str]:
    """
    Calculates the optimal entry price based on all 5 checks.

    Strategy:
    - If EMA cross is fresh → enter at market (best opportunity)
    - If pullback pending → set limit order at EMA9 level
    - If H1 overbought → tighten entry, wait for pullback
    - If structure break → enter at breakout level + small buffer
    - Default → current market price
    """
    try:
        import pandas_ta as ta
        ema9  = ta.ema(df["close"], length=9).iloc[-2]
        atr   = ta.atr(df["high"], df["low"], df["close"], length=14).iloc[-2]
        pip   = 0.01 if ("JPY" in pair.upper() or "XAU" in pair.upper()) else 0.0001

        # Fresh EMA cross → market entry
        if ema_result.get("just_crossed"):
            return round(current_price, 5), "Fresh EMA cross — market entry"

        # H1 overbought/oversold → wait for better price
        h1_signal = h1_result.get("signal", "")
        if h1_signal in ("OVERBOUGHT", "OVERSOLD"):
            if direction == "BUY":
                optimal = round(ema9 + atr * 0.1, 5)
                return optimal, f"H1 overbought — limit entry near EMA9 ({optimal:.5f})"
            else:
                optimal = round(ema9 - atr * 0.1, 5)
                return optimal, f"H1 oversold — limit entry near EMA9 ({optimal:.5f})"

        # Pre-cross anticipation → slightly better price
        if ema_result.get("type") == "PRE_CROSS":
            if direction == "BUY":
                optimal = round(min(current_price, ema9 + atr * 0.15), 5)
            else:
                optimal = round(max(current_price, ema9 - atr * 0.15), 5)
            return optimal, f"Pre-cross anticipation entry at {optimal:.5f}"

        # Structure break → enter just beyond the broken level
        level = structure_result.get("level")
        if level and structure_result.get("quality", 0) >= 70:
            buffer = atr * 0.05
            if direction == "BUY":
                optimal = round(level + buffer, 5)
            else:
                optimal = round(level - buffer, 5)
            return optimal, f"Structure break entry at {optimal:.5f}"

        # Default: current market price
        return round(current_price, 5), "Standard market entry"

    except Exception as e:
        logger.debug(f"Optimal entry calc error: {e}")
        return round(current_price, 5), "Fallback market entry"


# ─────────────────────────────────────────────────────────────────────────────
# MASTER FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def run_early_entry_analysis(
    df_m15: pd.DataFrame,
    direction: str,
    current_price: float,
    pair: str,
    df_h1: Optional[pd.DataFrame] = None,
    divergence_context: Optional[dict] = None,
) -> dict:
    """
    Runs all 5 early entry checks and returns a consolidated result.

    `divergence_context`: pass {"confirmed": True, ...} when the trade's
    basis is signal_engine.py's DIVERGENCE_RETEST trigger — a confirmed
    retest already did equivalent "wait for the right moment" work, so this
    avoids re-penalizing/re-delaying it via these independent timing checks.

    Returns:
    {
        "entry_quality":    0-100,
        "optimal_entry":    float,
        "entry_type":       "IMMEDIATE" | "LIMIT" | "WAIT",
        "confidence_bonus": 0-25,
        "pips_saved":       float,
        "checks":           dict,
        "summary":          str,
    }
    """
    # Run all 5 detectors
    ema_result       = detect_ema_cross_anticipation(df_m15, direction)
    candle_result    = check_candle_close_quality(df_m15, direction)
    h1_result        = check_h1_momentum(df_h1, direction)
    flow_result      = detect_order_flow_imbalance(df_m15, direction)
    structure_result = detect_micro_structure_break(df_m15, direction, pair)

    # Weighted quality score
    quality = (
        ema_result.get("quality",       50) * 0.25 +
        candle_result.get("quality",    50) * 0.20 +
        h1_result.get("quality",        50) * 0.25 +
        flow_result.get("quality",      50) * 0.15 +
        structure_result.get("quality", 50) * 0.15
    )
    quality = round(quality, 1)

    # Confidence bonus: 0-25 pts based on entry quality
    if quality >= 80:
        confidence_bonus = 25
    elif quality >= 70:
        confidence_bonus = 18
    elif quality >= 60:
        confidence_bonus = 10
    elif quality >= 50:
        confidence_bonus = 5
    else:
        confidence_bonus = 0

    # Entry type
    h1_signal   = h1_result.get("signal", "NEUTRAL")
    overbought  = h1_signal in ("OVERBOUGHT", "OVERSOLD")
    doji        = candle_result.get("body_pct", 0.5) < 0.2

    if overbought or doji:
        entry_type = "WAIT"
    elif quality >= 70:
        entry_type = "IMMEDIATE"
    else:
        entry_type = "LIMIT"

    # A confirmed divergence+retest already did the "wait for the right
    # moment" work (that's the whole point of requiring a retest) — don't
    # let these independent, redundant timing checks stall it further.
    divergence_confirmed = bool(divergence_context and divergence_context.get("confirmed"))
    if divergence_confirmed:
        confidence_bonus = min(25, confidence_bonus + 5)
        if entry_type == "WAIT":
            entry_type = "IMMEDIATE"

    # Optimal entry price
    optimal_entry, entry_reason = calculate_optimal_entry(
        df_m15, direction, current_price, pair,
        ema_result, candle_result, h1_result, flow_result, structure_result
    )

    # Pips saved vs normal late entry
    pip = 0.01 if ("JPY" in pair.upper() or "XAU" in pair.upper()) else 0.0001
    pips_saved = round(abs(current_price - optimal_entry) / pip, 1)
    pips_saved = max(pips_saved, ema_result.get("pips_saved", 0))

    # Summary
    reasons = []
    if ema_result.get("type") not in ("none", None):
        reasons.append(ema_result.get("type", ""))
    if h1_result.get("signal") in ("EARLY", "CONFIRMED"):
        reasons.append(f"H1-{h1_result['signal']}")
    if structure_result.get("type"):
        reasons.append(structure_result.get("type", ""))
    if flow_result.get("quality", 0) >= 70:
        reasons.append("strong-flow")
    if divergence_confirmed:
        reasons.append("divergence-retest-confirmed")

    summary = (
        f"{pair} {direction} | EntryQ={quality:.0f} | "
        f"Type={entry_type} | Bonus=+{confidence_bonus}pts | "
        f"Entry={optimal_entry:.5f} | ~{pips_saved:.0f}p earlier"
    )
    if reasons:
        summary += f" | {', '.join(reasons)}"

    logger.info(f"[EarlyEntry] {summary}")

    return {
        "entry_quality":    quality,
        "optimal_entry":    optimal_entry,
        "entry_type":       entry_type,
        "confidence_bonus": confidence_bonus,
        "pips_saved":       pips_saved,
        "entry_reason":     entry_reason,
        "checks": {
            "ema_cross":  ema_result,
            "candle":     candle_result,
            "h1_momentum": h1_result,
            "order_flow": flow_result,
            "structure":  structure_result,
        },
        "summary": summary,
    }
