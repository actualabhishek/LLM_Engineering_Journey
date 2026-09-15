"""
precision_entry.py
------------------
7 precision entry improvements that run AFTER the main signal is confirmed
but BEFORE order execution. Each check either:
  - Blocks the trade (returns False)
  - Improves the entry price (returns a better price)
  - Adds bonus confidence points
  - Adjusts lot size

Improvements:
  1. D1/H4 Hard Bias Lock      — no trades against the higher timeframe trend
  2. Pullback Entry Timing      — wait for price to retrace to EMA before entry
  3. Volume Confirmation        — require above-average volume on signal candle
  4. Liquidity Sweep Detection  — detect stop hunts and FVGs for best entries
  5. Momentum Divergence Filter — skip if RSI diverges from price
  6. Dynamic Lot Sizing         — scale size with conviction score
  7. Session Profile Filters    — London open breakout / NY fade / dead zone skip
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Optional
from core.config_manager import config
from core.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. D1 / H4 HARD BIAS LOCK
# ─────────────────────────────────────────────────────────────────────────────

def check_higher_tf_bias(mtf_analysis: dict, direction: str) -> tuple[bool, str]:
    """
    Hard rule: D1 and H4 must not strongly oppose the trade direction.

    Rules:
      - If D1 is SELL and we want to BUY → BLOCK (counter D1 trend)
      - If H4 is SELL and D1 is SELL and we want to BUY → BLOCK (hard counter)
      - If D1 is BUY and H4 is BUY → ALLOW with bonus note
      - D1 neutral + H4 aligned → ALLOW
      - Only M15 aligned → ALLOW but no bonus (already handled in confidence)

    Returns: (allowed: bool, reason: str)
    """
    tf_results = mtf_analysis.get("tf_results", {})
    d1_dir  = tf_results.get("D1",  {}).get("simple_direction", "NEUTRAL")
    h4_dir  = tf_results.get("H4",  {}).get("simple_direction", "NEUTRAL")
    h1_dir  = tf_results.get("H1",  {}).get("simple_direction", "NEUTRAL")

    opposite = "SELL" if direction == "BUY" else "BUY"

    # Hard block: D1 directly opposes our direction
    if d1_dir == opposite:
        return False, f"D1 is {d1_dir} — hard bias blocks {direction} entry"

    # Hard block: H4 + H1 both oppose and D1 is neutral
    if h4_dir == opposite and h1_dir == opposite and d1_dir == "NEUTRAL":
        return False, f"H4+H1 both {opposite} with neutral D1 — too risky for {direction}"

    # Soft warning (logged but allowed): only H4 opposes
    if h4_dir == opposite and d1_dir != opposite:
        logger.debug(f"H4 counter-trend ({opposite}) but D1 neutral/aligned — allowing with caution")

    return True, f"Higher TF bias OK: D1={d1_dir} H4={h4_dir}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. PULLBACK ENTRY TIMING
# ─────────────────────────────────────────────────────────────────────────────

def get_pullback_entry(
    df: pd.DataFrame,
    direction: str,
    current_price: float,
    pair: str,
) -> tuple[bool, float, str]:
    """
    Check whether the current candle is already at a good entry (pulled back
    to EMA9 or EMA21) or has overextended. If overextended, returns the
    EMA level as the ideal entry price to wait for.

    Returns: (enter_now: bool, ideal_entry: float, reason: str)
    """
    try:
        if len(df) < 25:
            return True, current_price, "Insufficient data for pullback check"

        import pandas_ta as ta
        ema9  = ta.ema(df["close"], length=9).iloc[-2]
        ema21 = ta.ema(df["close"], length=21).iloc[-2]
        atr   = ta.atr(df["high"], df["low"], df["close"], length=14).iloc[-2]
        pip   = 0.01 if ("JPY" in pair.upper() or "XAU" in pair.upper()) else 0.0001

        # Distance from current price to each EMA in pips
        dist_ema9  = abs(current_price - ema9)  / pip
        dist_ema21 = abs(current_price - ema21) / pip
        atr_pips   = atr / pip

        if direction == "BUY":
            # Ideal entry: price near or just above EMA9 or EMA21
            overextended = current_price > ema9 + atr * 0.8  # more than 0.8 ATR above EMA9
            at_ema = dist_ema9 <= atr_pips * 0.4 or dist_ema21 <= atr_pips * 0.5

            if at_ema:
                return True, current_price, f"Price at EMA ({dist_ema9:.1f} pips from EMA9) — ideal pullback entry"
            elif overextended:
                ideal = round(ema9 + atr * 0.1, 5)   # just above EMA9
                logger.info(f"[Pullback] {pair} BUY overextended by {dist_ema9:.1f}p — ideal entry near {ideal:.5f}")
                return False, ideal, f"Price {dist_ema9:.1f}p above EMA9 — wait for pullback to {ideal:.5f}"
            else:
                return True, current_price, "Acceptable entry — within ATR of EMA"

        else:  # SELL
            overextended = current_price < ema9 - atr * 0.8
            at_ema = dist_ema9 <= atr_pips * 0.4 or dist_ema21 <= atr_pips * 0.5

            if at_ema:
                return True, current_price, f"Price at EMA ({dist_ema9:.1f} pips from EMA9) — ideal pullback entry"
            elif overextended:
                ideal = round(ema9 - atr * 0.1, 5)
                logger.info(f"[Pullback] {pair} SELL overextended by {dist_ema9:.1f}p — ideal entry near {ideal:.5f}")
                return False, ideal, f"Price {dist_ema9:.1f}p below EMA9 — wait for pullback to {ideal:.5f}"
            else:
                return True, current_price, "Acceptable entry — within ATR of EMA"

    except Exception as e:
        logger.debug(f"Pullback check error: {e}")
        return True, current_price, "Pullback check skipped"


# ─────────────────────────────────────────────────────────────────────────────
# 3. VOLUME CONFIRMATION
# ─────────────────────────────────────────────────────────────────────────────

def check_volume_confirmation(df: pd.DataFrame, direction: str) -> tuple[bool, int, str]:
    """
    Confirms that the signal candle has meaningful volume.
    Forex tick volume is a proxy for real volume — not perfect but directional.

    Returns: (confirmed: bool, volume_score: 0-20, reason: str)
    """
    try:
        if "volume" not in df.columns or len(df) < 20:
            return True, 10, "Volume data unavailable — skipping check"

        vol = df["volume"]
        avg_vol   = vol.iloc[-20:-1].mean()
        last_vol  = vol.iloc[-2]   # last closed candle
        prev_vol  = vol.iloc[-3]

        if avg_vol <= 0:
            return True, 10, "Zero average volume — skipping"

        ratio = last_vol / avg_vol

        # Volume spike on signal candle (strong confirmation)
        if ratio >= 1.8:
            score = 20
            msg = f"Strong volume spike: {ratio:.1f}x average — high conviction"
        elif ratio >= 1.3:
            score = 15
            msg = f"Above-average volume: {ratio:.1f}x — good confirmation"
        elif ratio >= 0.8:
            score = 8
            msg = f"Normal volume: {ratio:.1f}x average"
        else:
            # Low volume breakout — often fake
            score = 0
            msg = f"Low volume breakout: {ratio:.1f}x average — potential fake-out"
            logger.info(f"[Volume] Thin volume signal ({ratio:.1f}x avg) — reduced confidence")
            # Don't block, just reduce score — low volume is a warning not a hard stop
            return True, score, msg

        return True, score, msg

    except Exception as e:
        logger.debug(f"Volume check error: {e}")
        return True, 10, "Volume check skipped"


# ─────────────────────────────────────────────────────────────────────────────
# 4. LIQUIDITY SWEEP & FAIR VALUE GAP DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_liquidity_sweep(df: pd.DataFrame, pair: str) -> dict:
    """
    Detects two high-probability Smart Money setups:

    A) Stop Hunt / Liquidity Sweep:
       - Price briefly breaks a swing high/low then closes back inside
       - This is institutions taking retail stop losses before reversing
       - Long wick + close back inside = high probability reversal

    B) Fair Value Gap (FVG / Imbalance):
       - 3-candle pattern where candle 1 high < candle 3 low (bullish FVG)
       - Price leaving a gap it will return to fill
       - Entry when price returns to the FVG zone

    Returns: {signal, confidence_bonus, pattern, entry_zone, detail}
    """
    try:
        if len(df) < 10:
            return {"signal": "NEUTRAL", "confidence_bonus": 0, "pattern": "none"}

        c1 = df.iloc[-4]  # 3 bars ago
        c2 = df.iloc[-3]  # 2 bars ago
        c3 = df.iloc[-2]  # last closed bar (signal candle)
        pip = 0.01 if ("JPY" in pair.upper() or "XAU" in pair.upper()) else 0.0001
        atr = (df["high"] - df["low"]).rolling(14).mean().iloc[-2]

        # ── A. Bullish Stop Hunt (wick below swing low then closes up) ──
        lower_wick = min(c3["close"], c3["open"]) - c3["low"]
        upper_wick = c3["high"] - max(c3["close"], c3["open"])
        body = abs(c3["close"] - c3["open"])

        if (lower_wick > atr * 0.6 and           # significant lower wick
            lower_wick > upper_wick * 2 and       # wick dominates
            c3["close"] > c3["open"] and           # closed bullish
            body > atr * 0.1):                     # real body, not doji
            sweep_pips = lower_wick / pip
            bonus = min(20, int(sweep_pips / 2))
            return {
                "signal": "BUY",
                "confidence_bonus": bonus,
                "pattern": "Bullish Liquidity Sweep",
                "entry_zone": round(c3["close"], 5),
                "detail": f"Swept {sweep_pips:.1f}p below, closed bullish",
            }

        # ── A. Bearish Stop Hunt ──
        if (upper_wick > atr * 0.6 and
            upper_wick > lower_wick * 2 and
            c3["close"] < c3["open"] and
            body > atr * 0.1):
            sweep_pips = upper_wick / pip
            bonus = min(20, int(sweep_pips / 2))
            return {
                "signal": "SELL",
                "confidence_bonus": bonus,
                "pattern": "Bearish Liquidity Sweep",
                "entry_zone": round(c3["close"], 5),
                "detail": f"Swept {sweep_pips:.1f}p above, closed bearish",
            }

        # ── B. Bullish FVG (gap between c1 high and c3 low) ──
        if c1["high"] < c3["low"] and (c3["low"] - c1["high"]) > atr * 0.3:
            fvg_top    = c3["low"]
            fvg_bottom = c1["high"]
            fvg_mid    = (fvg_top + fvg_bottom) / 2
            current    = df.iloc[-1]["close"]
            # Price returning into FVG = entry
            if fvg_bottom <= current <= fvg_top + atr * 0.2:
                return {
                    "signal": "BUY",
                    "confidence_bonus": 15,
                    "pattern": "Bullish Fair Value Gap",
                    "entry_zone": round(fvg_mid, 5),
                    "detail": f"FVG {fvg_bottom:.5f}–{fvg_top:.5f}, price returned to fill",
                }

        # ── B. Bearish FVG ──
        if c1["low"] > c3["high"] and (c1["low"] - c3["high"]) > atr * 0.3:
            fvg_bottom = c3["high"]
            fvg_top    = c1["low"]
            fvg_mid    = (fvg_top + fvg_bottom) / 2
            current    = df.iloc[-1]["close"]
            if fvg_bottom - atr * 0.2 <= current <= fvg_top:
                return {
                    "signal": "SELL",
                    "confidence_bonus": 15,
                    "pattern": "Bearish Fair Value Gap",
                    "entry_zone": round(fvg_mid, 5),
                    "detail": f"FVG {fvg_bottom:.5f}–{fvg_top:.5f}, price returned to fill",
                }

        return {"signal": "NEUTRAL", "confidence_bonus": 0, "pattern": "none"}

    except Exception as e:
        logger.debug(f"Liquidity sweep error: {e}")
        return {"signal": "NEUTRAL", "confidence_bonus": 0, "pattern": "none"}


# ─────────────────────────────────────────────────────────────────────────────
# 5. MOMENTUM DIVERGENCE FILTER
# ─────────────────────────────────────────────────────────────────────────────

def check_chase_divergence(df: pd.DataFrame, direction: str) -> tuple[bool, str]:
    """
    "Don't chase" guard: detects hidden weakness/strength via RSI divergence
    AGAINST the trade direction, to avoid entering just as the move runs out
    of steam. This is the opposite use of divergence from
    strategies/divergence_retest.py::detect_rsi_divergence(), which uses a
    confirmed divergence+retest as a proactive REASON to enter. Same
    underlying pattern, opposite role — don't conflate the two.

    Bearish divergence (BUY signal but bearish div → SKIP):
      Price makes higher high but RSI makes lower high

    Bullish divergence (SELL signal but bullish div → SKIP):
      Price makes lower low but RSI makes higher low

    Returns: (no_divergence: bool, reason: str)
    """
    try:
        import pandas_ta as ta
        if len(df) < 30:
            return True, "Insufficient data for divergence check"

        rsi = ta.rsi(df["close"], length=14)
        price = df["close"]

        # Look at last 2 swing points (simplified: compare last 2 peaks/troughs)
        lookback = 15
        price_window = price.iloc[-lookback:]
        rsi_window   = rsi.iloc[-lookback:]

        if direction == "BUY":
            # Check for bearish divergence: price HH, RSI LH
            price_recent_high = price_window.iloc[-5:].max()
            price_prev_high   = price_window.iloc[:10].max()
            rsi_recent_high   = rsi_window.iloc[-5:].max()
            rsi_prev_high     = rsi_window.iloc[:10].max()

            if (price_recent_high > price_prev_high * 1.0002 and  # price made HH
                rsi_recent_high < rsi_prev_high - 3):              # RSI made LH
                return False, f"Bearish RSI divergence — price HH but RSI falling ({rsi_recent_high:.0f} vs {rsi_prev_high:.0f})"

        else:  # SELL
            # Check for bullish divergence: price LL, RSI HL
            price_recent_low = price_window.iloc[-5:].min()
            price_prev_low   = price_window.iloc[:10].min()
            rsi_recent_low   = rsi_window.iloc[-5:].min()
            rsi_prev_low     = rsi_window.iloc[:10].min()

            if (price_recent_low < price_prev_low * 0.9998 and   # price made LL
                rsi_recent_low > rsi_prev_low + 3):              # RSI made HL
                return False, f"Bullish RSI divergence — price LL but RSI rising ({rsi_recent_low:.0f} vs {rsi_prev_low:.0f})"

        return True, "No momentum divergence detected"

    except Exception as e:
        logger.debug(f"Divergence check error: {e}")
        return True, "Divergence check skipped"


# ─────────────────────────────────────────────────────────────────────────────
# 6. DYNAMIC LOT SIZING
# ─────────────────────────────────────────────────────────────────────────────

def calculate_dynamic_lots(
    score: float,
    base_lot: float,
    account_balance: float,
    sl_pips: float,
    pair: str,
    pattern_count: int = 0,
) -> tuple[float, str]:
    """
    Scales lot size with conviction level.

    Tiers (as fraction of max_risk_pct):
      Score 65-74, 1 pattern  → 50% of max risk  (cautious)
      Score 75-84, 1 pattern  → 75% of max risk  (standard)
      Score 85+, 2+ patterns  → 100% of max risk (high conviction)
      Score 80+, liquidity sweep confirmed → 110% (capped at max)

    Always bounded by config min_lot and max_lot.
    """
    try:
        max_risk_pct = config.get("risk", "max_risk_pct") or 1.0
        min_lot      = config.get("trading", "default_lot_size") or 0.02  # respect default lot
        max_lot      = config.get("risk", "max_lot_size") or 0.10

        # Pip value per lot (approximate, USD account)
        pip_val = 10.0 if "JPY" not in pair.upper() else 9.1   # per standard lot
        risk_per_lot = sl_pips * pip_val                         # $ risk per 1.0 lot

        if risk_per_lot <= 0:
            return base_lot, "Could not calculate dynamic lot — using base"

        max_risk_usd = account_balance * (max_risk_pct / 100)

        # Conviction multiplier
        if score >= 85 and pattern_count >= 2:
            multiplier = 1.0       # full risk
            tier = "HIGH conviction"
        elif score >= 75:
            multiplier = 0.75      # standard
            tier = "STANDARD conviction"
        else:
            multiplier = 0.50      # cautious
            tier = "CAUTIOUS conviction"

        risk_usd = max_risk_usd * multiplier
        raw_lots = risk_usd / risk_per_lot

        # Round to nearest 0.01, then clamp
        lots = round(max(min_lot, min(max_lot, round(raw_lots, 2))), 2)
        reason = f"{tier} (score={score:.0f}, {pattern_count} patterns) → {lots} lots"
        return lots, reason

    except Exception as e:
        logger.debug(f"Dynamic lot sizing error: {e}")
        return base_lot, "Dynamic sizing failed — using base lot"


# ─────────────────────────────────────────────────────────────────────────────
# 7. SESSION PROFILE FILTERS
# ─────────────────────────────────────────────────────────────────────────────

ASIAN_RANGE_HOURS   = range(0, 7)    # 00:00–07:00 UTC
LONDON_OPEN_HOURS   = range(7, 9)    # 07:00–09:00 UTC (breakout window)
LONDON_BODY_HOURS   = range(9, 12)   # 09:00–12:00 UTC (trend continuation)
DEAD_ZONE_HOURS     = range(12, 13)  # 12:00–13:00 UTC (low liquidity)
NY_OPEN_HOURS       = range(13, 15)  # 13:00–15:00 UTC (NY open, trend/fade)
NY_BODY_HOURS       = range(15, 20)  # 15:00–20:00 UTC (trend continuation)
OFF_HOURS           = range(20, 24)  # 20:00–00:00 UTC (avoid)


def check_session_profile(
    direction: str,
    df_m15: pd.DataFrame,
    df_h1: Optional[pd.DataFrame] = None,
) -> tuple[bool, int, str]:
    """
    Session-specific entry filters and bonuses.

    Returns: (allowed: bool, confidence_bonus: int, reason: str)
    """
    now = datetime.now(timezone.utc)
    hour = now.hour

    # ── Dead zone: 12:00–13:00 UTC ──
    if hour in DEAD_ZONE_HOURS:
        return False, 0, "Dead zone (12:00–13:00 UTC) — low liquidity, skipping"

    # ── Off-hours: 20:00–00:00 UTC ──
    if hour in OFF_HOURS:
        return False, 0, "Off-hours (20:00–00:00 UTC) — skipping"

    # ── London open breakout: 07:00–09:00 UTC ──
    if hour in LONDON_OPEN_HOURS:
        bonus, reason = _london_open_check(direction, df_m15)
        return True, bonus, reason

    # ── NY open: 13:00–15:00 UTC — favour reversals of London move ──
    if hour in NY_OPEN_HOURS:
        bonus, reason = _ny_open_check(direction, df_m15, df_h1)
        return True, bonus, reason

    # ── Core trading hours: London body + NY body ──
    if hour in LONDON_BODY_HOURS or hour in NY_BODY_HOURS:
        return True, 5, f"Core session hour {hour}:xx UTC — trend continuation"

    # Asian session: only very high confidence
    if hour in ASIAN_RANGE_HOURS:
        return True, -5, "Asian session — reduced confidence bonus"

    return True, 0, "Standard session"


def _london_open_check(direction: str, df: pd.DataFrame) -> tuple[int, str]:
    """
    London open strategy: Asian range box breakout.
    The Asian session (00:00–07:00 UTC) forms a range.
    London breaks above resistance → BUY, below support → SELL.
    """
    try:
        if len(df) < 28:
            return 5, "London open — insufficient data for Asian range"

        # Asian session candles = approximately last 28 M15 bars (7 hours)
        asian_bars = df.iloc[-30:-2]
        asian_high = asian_bars["high"].max()
        asian_low  = asian_bars["low"].min()
        current    = df.iloc[-2]["close"]
        atr        = (df["high"] - df["low"]).rolling(14).mean().iloc[-2]

        if direction == "BUY" and current > asian_high + atr * 0.1:
            return 15, f"London open breakout above Asian high ({asian_high:.5f}) ✓"
        elif direction == "SELL" and current < asian_low - atr * 0.1:
            return 15, f"London open breakdown below Asian low ({asian_low:.5f}) ✓"
        else:
            return 3, "London open — not a clean Asian range breakout"
    except Exception:
        return 3, "London open check failed"


def _ny_open_check(
    direction: str,
    df_m15: pd.DataFrame,
    df_h1: Optional[pd.DataFrame],
) -> tuple[int, str]:
    """
    NY open strategy: often fades the London move.
    Check if the London session trended strongly — if so, this direction
    is a continuation. If NY is reversing London, apply a small penalty.
    """
    try:
        if df_h1 is None or len(df_h1) < 10:
            return 5, "NY open — no H1 data for London move check"

        # London move: H1 bars from ~07:00–12:00 = approximately last 5 H1 bars
        london_bars = df_h1.iloc[-6:-1]
        london_open_price = london_bars.iloc[0]["open"]
        london_close_price = london_bars.iloc[-1]["close"]
        london_direction = "BUY" if london_close_price > london_open_price else "SELL"

        if direction == london_direction:
            return 8, f"NY continuation of London {london_direction} move"
        else:
            # NY reversing London — this can be valid but apply caution
            return -3, f"NY reversing London {london_direction} — caution applied"
    except Exception:
        return 5, "NY open check failed"


# ─────────────────────────────────────────────────────────────────────────────
# MASTER FUNCTION — runs all 7 checks
# ─────────────────────────────────────────────────────────────────────────────

def run_precision_checks(
    direction: str,
    pair: str,
    current_price: float,
    base_score: float,
    base_lot: float,
    sl_pips: float,
    mtf_analysis: dict,
    df_m15: pd.DataFrame,
    df_h1: Optional[pd.DataFrame] = None,
    account_balance: float = 100.0,
    pattern_count: int = 0,
    trigger_name: str = "",
) -> dict:
    """
    Runs all precision entry checks and returns a consolidated result.

    Returns:
    {
        "allowed":          bool,    # False = skip this trade
        "block_reason":     str,     # why it was blocked (if allowed=False)
        "adjusted_score":   float,   # base_score + all bonuses/penalties
        "recommended_lots": float,   # dynamically sized lot
        "enter_now":        bool,    # False = wait for pullback
        "ideal_entry":      float,   # price to wait for (if not enter_now)
        "bonuses":          dict,    # breakdown of score adjustments
        "summary":          str,     # human-readable log line
    }
    """
    bonuses = {}
    blocks  = []

    # ── Check 1: D1/H4 Hard Bias ──
    bias_ok, bias_reason = check_higher_tf_bias(mtf_analysis, direction)
    if not bias_ok:
        return {
            "allowed": False, "block_reason": bias_reason,
            "adjusted_score": base_score, "recommended_lots": base_lot,
            "enter_now": False, "ideal_entry": current_price,
            "bonuses": {}, "summary": f"BLOCKED: {bias_reason}",
        }
    bonuses["higher_tf_bias"] = 0

    # ── Check 2: Pullback Entry Timing ──
    enter_now, ideal_entry, pullback_reason = get_pullback_entry(
        df_m15, direction, current_price, pair
    )
    bonuses["pullback"] = 5 if enter_now and "ideal" in pullback_reason.lower() else 0

    # ── Check 3: Volume Confirmation ──
    # Normally a soft score input (forex tick volume isn't real volume, so a
    # thin reading alone shouldn't veto an otherwise strong structural setup).
    # Exception: a retest entry with NO volume confirmation is the classic
    # false-retest failure mode, so it's a hard requirement specifically for
    # the divergence/retest trigger type.
    vol_ok, vol_score, vol_reason = check_volume_confirmation(df_m15, direction)
    if "DIVERGENCE_RETEST" in trigger_name and vol_score == 0:
        # NOTE: must contain the lowercase substring "divergence" — the
        # orchestrator's precision-block gate matches on it to decide this
        # is a hard skip, not a soft/HTF-only block (see trading_orchestrator.py).
        block_reason = f"No volume confirmation for this divergence retest — {vol_reason}"
        return {
            "allowed": False, "block_reason": block_reason,
            "adjusted_score": base_score, "recommended_lots": base_lot,
            "enter_now": False, "ideal_entry": current_price,
            "bonuses": {}, "summary": f"BLOCKED: {block_reason}",
        }
    bonuses["volume"] = vol_score - 10   # normalise: avg vol = 0 bonus

    # ── Check 4: Liquidity Sweep / FVG ──
    liq = detect_liquidity_sweep(df_m15, pair)
    liq_bonus = 0
    if liq["signal"] == direction:
        liq_bonus = liq.get("confidence_bonus", 0)
        logger.info(f"[Precision] {pair} {liq['pattern']}: +{liq_bonus}pts")
    elif liq["signal"] not in ("NEUTRAL", "none") and liq["signal"] != direction:
        liq_bonus = -10   # opposing liquidity signal
    bonuses["liquidity_sweep"] = liq_bonus

    # ── Check 5: Chase-Divergence Guard ──
    no_div, div_reason = check_chase_divergence(df_m15, direction)
    if not no_div:
        return {
            "allowed": False, "block_reason": div_reason,
            "adjusted_score": base_score, "recommended_lots": base_lot,
            "enter_now": False, "ideal_entry": current_price,
            "bonuses": bonuses, "summary": f"BLOCKED: {div_reason}",
        }
    bonuses["divergence"] = 0

    # ── Check 7: Session Profile ──
    sess_ok, sess_bonus, sess_reason = check_session_profile(direction, df_m15, df_h1)
    if not sess_ok:
        return {
            "allowed": False, "block_reason": sess_reason,
            "adjusted_score": base_score, "recommended_lots": base_lot,
            "enter_now": False, "ideal_entry": current_price,
            "bonuses": bonuses, "summary": f"BLOCKED: {sess_reason}",
        }
    bonuses["session_profile"] = sess_bonus

    # ── Total adjusted score ──
    total_bonus = sum(bonuses.values())
    adjusted_score = round(min(100, max(0, base_score + total_bonus)), 1)

    # ── Check 6: Dynamic Lot Sizing ──
    recommended_lots, lot_reason = calculate_dynamic_lots(
        adjusted_score, base_lot, account_balance, sl_pips, pair, pattern_count
    )

    # ── Summary ──
    bonus_str = " ".join(f"{k}:{v:+d}" for k, v in bonuses.items() if v != 0)
    liq_str = f" | {liq['pattern']}" if liq["signal"] == direction else ""
    summary = (
        f"{pair} {direction} | Base={base_score:.0f} Bonus={total_bonus:+d} "
        f"→ {adjusted_score:.0f} | Lots={recommended_lots}{liq_str}"
    )

    if not enter_now:
        summary += f" | ⏳ Wait pullback to {ideal_entry:.5f}"

    logger.info(f"[Precision] {summary}")

    return {
        "allowed":          True,
        "block_reason":     "",
        "adjusted_score":   adjusted_score,
        "recommended_lots": recommended_lots,
        "enter_now":        enter_now,
        "ideal_entry":      ideal_entry,
        "bonuses":          bonuses,
        "liquidity_pattern": liq.get("pattern", "none"),
        "volume_ratio":     vol_reason,
        "session_reason":   sess_reason,
        "summary":          summary,
    }
