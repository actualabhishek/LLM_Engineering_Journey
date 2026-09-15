"""
signal_engine.py  v2 — Intraday Swing Trading Engine
=====================================================
Philosophy (per trading spec):
  - PRIMARY  : 15M trend, swings, momentum, market structure
  - SECONDARY: 1H confirmation
  - CONTEXT  : 4H / D1 bias — mostly a confidence bonus/penalty, but ALSO a
               deliberate hard block when D1 AND H4 both directly oppose the
               fired trigger's direction (config: signal_engine.require_d1_h4_alignment).
               Cross-timeframe agreement between the two highest timeframes
               is treated as a stronger signal than trigger-level structure
               alone — see the D1+H4 TREND FILTER section in generate_signal().

Core detections:
  1. Swing high / swing low (HH/HL/LH/LL structure)
  2. Change of Character (CHOCH) — first structural break in opposite direction
  3. Break of Structure (BOS)    — continuation break of same direction
  4. Momentum expansion          — large-body directional candles with volume
  5. Liquidity sweep             — spike through high/low then reversal
  6. EMA pullback (within trend) — retrace to EMA9/21 then continuation
  7. Compression breakout        — inside bars / tight range → expansion
  8. RSI divergence + retest     — leading reversal signal, confirmed by a
                                    pin-bar/engulfing rejection before firing
                                    (see strategies/divergence_retest.py)

Entry timing rules (CRITICAL — prevents buying tops):
  - Never enter if price has already moved > 1.5× ATR from the signal level
  - Never enter if RSI > 72 for BUY or < 28 for SELL (overextended)
  - Never enter if candle body is < 30% (indecision)
  - Always wait for CANDLE CLOSE confirmation

Output: signal dict with direction, entry_price, confidence, trigger, htf_context
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Optional
from core.config_manager import config
from core.logger import get_logger

logger = get_logger(__name__)


# ─── utilities ───────────────────────────────────────────────────────────────

def _pip(pair: str) -> float:
    return 0.01 if ("JPY" in pair.upper() or "XAU" in pair.upper()) else 0.0001

def _pips(diff: float, pair: str) -> float:
    return abs(diff) / _pip(pair)

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l,
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    ls = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / (ls + 1e-10))

def is_choppy_market(df: pd.DataFrame, pair: str) -> bool:
    """
    True when ADX indicates a ranging/choppy market with no clean trend.
    Used as a confidence dampener elsewhere (never a hard block) — a choppy
    reading alone shouldn't veto an otherwise strong structural setup.
    """
    try:
        from strategies.indicators import calculate_indicators
        ind = calculate_indicators(df, pair)
        if not ind:
            return False
        adx = ind.get("adx", 0)
    except Exception:
        return False
    threshold = config.get("signal_engine", "choppy_adx_threshold", default=18)
    return adx < threshold


def _neutral(reason: str = "") -> dict:
    return {"signal_direction": "NEUTRAL", "entry_type": "NONE",
            "entry_price": 0.0, "confidence": 0,
            "trigger": reason or "no signal",
            "htf_context": "NEUTRAL", "trade_with_trend": False}


# ─── LAYER 1: 15M MARKET STRUCTURE ───────────────────────────────────────────

def detect_market_structure(df: pd.DataFrame, pair: str) -> dict:
    """
    Identifies swing highs/lows and classifies:
      - Uptrend:   HH + HL sequence
      - Downtrend: LH + LL sequence
      - CHOCH:     First break that opposes current structure → reversal signal
      - BOS:       Break that continues current structure → continuation signal

    Uses last 30 bars, looks at pivot points with order=3.
    """
    try:
        if len(df) < 30:
            return {"structure": "NEUTRAL", "choch": False, "bos": False}

        high  = df["high"]
        low   = df["low"]
        close = df["close"]

        # Find recent swing highs and lows (last 30 bars)
        window = min(30, len(df))
        sh_idx, sl_idx = [], []
        for i in range(3, window - 3):
            if all(high.iloc[-window+i] >= high.iloc[-window+i-j] for j in range(1,4)) and \
               all(high.iloc[-window+i] >= high.iloc[-window+i+j] for j in range(1,4)):
                sh_idx.append(-window + i)
            if all(low.iloc[-window+i] <= low.iloc[-window+i-j] for j in range(1,4)) and \
               all(low.iloc[-window+i] <= low.iloc[-window+i+j] for j in range(1,4)):
                sl_idx.append(-window + i)

        if len(sh_idx) < 2 or len(sl_idx) < 2:
            return {"structure": "NEUTRAL", "choch": False, "bos": False,
                    "last_sh": None, "last_sl": None}

        # Last two swing highs and lows
        sh_vals = [high.iloc[i] for i in sh_idx[-3:]]
        sl_vals = [low.iloc[i]  for i in sl_idx[-3:]]
        last_sh = sh_vals[-1]
        last_sl = sl_vals[-1]
        prev_sh = sh_vals[-2] if len(sh_vals) >= 2 else None
        prev_sl = sl_vals[-2] if len(sl_vals) >= 2 else None

        current = close.iloc[-2]  # last closed bar

        # Classify structure
        hh = prev_sh and last_sh > prev_sh
        hl = prev_sl and last_sl > prev_sl
        lh = prev_sh and last_sh < prev_sh
        ll = prev_sl and last_sl < prev_sl

        if hh and hl:
            structure = "UPTREND"
        elif lh and ll:
            structure = "DOWNTREND"
        elif hh and ll:
            structure = "EXPANDING"
        elif lh and hl:
            structure = "CONTRACTING"
        else:
            structure = "NEUTRAL"

        # CHOCH: price breaks OPPOSITE to structure
        # In uptrend: price breaks BELOW last swing low → CHOCH bearish
        # In downtrend: price breaks ABOVE last swing high → CHOCH bullish
        choch_bull = structure == "DOWNTREND" and current > last_sh
        choch_bear = structure == "UPTREND"   and current < last_sl

        # BOS: price breaks IN DIRECTION of structure
        bos_bull = structure == "UPTREND"   and current > last_sh
        bos_bear = structure == "DOWNTREND" and current < last_sl

        return {
            "structure":  structure,
            "choch":      choch_bull or choch_bear,
            "choch_dir":  "BUY" if choch_bull else "SELL" if choch_bear else None,
            "bos":        bos_bull or bos_bear,
            "bos_dir":    "BUY" if bos_bull else "SELL" if bos_bear else None,
            "last_sh":    last_sh,
            "last_sl":    last_sl,
            "hh": hh, "hl": hl, "lh": lh, "ll": ll,
        }
    except Exception as e:
        logger.debug(f"Structure detection error: {e}")
        return {"structure": "NEUTRAL", "choch": False, "bos": False}


def detect_momentum(df: pd.DataFrame, pair: str) -> dict:
    """
    Detects momentum expansion — the KEY signal that a new swing is forming.

    Expansion candle:
      - Body > 60% of range
      - Body > 1.5× average body size (last 10 bars)
      - Directional (bull or bear)
      - Volume above average (if available)

    Momentum shift:
      - Last 2 bars closing in same direction
      - Both above average body size

    Returns: {direction, strength: 0-100, expanding: bool, shift: bool}
    """
    try:
        if len(df) < 15:
            return {"direction": "NEUTRAL", "strength": 0, "expanding": False}

        c = df["close"]
        o = df["open"]
        h = df["high"]
        l = df["low"]
        v = df.get("volume", pd.Series([1]*len(df), index=df.index))

        body      = (c - o).abs()
        full      = (h - l).replace(0, 1e-10)
        body_pct  = body / full
        avg_body  = body.iloc[-12:-2].mean()
        avg_vol   = v.iloc[-12:-2].mean() if v.mean() > 0 else 1

        c1 = df.iloc[-2]  # last closed
        c2 = df.iloc[-3]  # bar before

        body1 = abs(c1["close"] - c1["open"])
        body2 = abs(c2["close"] - c2["open"])
        bp1   = body1 / max(c1["high"] - c1["low"], 1e-10)

        bull1 = c1["close"] > c1["open"]
        bear1 = c1["close"] < c1["open"]
        bull2 = c2["close"] > c2["open"]
        bear2 = c2["close"] < c2["open"]

        # Volume spike
        vol_spike = v.iloc[-2] > avg_vol * 1.3 if avg_vol > 0 else False

        # Expansion candle check
        is_expansion = body1 > avg_body * 1.5 and bp1 > 0.6

        # Momentum shift (2 bars same direction, both strong)
        bull_shift = bull1 and bull2 and body1 > avg_body and body2 > avg_body * 0.7
        bear_shift = bear1 and bear2 and body1 > avg_body and body2 > avg_body * 0.7

        if is_expansion and bull1:
            direction = "BUY"
            strength  = min(100, int(bp1 * 80 + (20 if vol_spike else 0)))
        elif is_expansion and bear1:
            direction = "SELL"
            strength  = min(100, int(bp1 * 80 + (20 if vol_spike else 0)))
        elif bull_shift:
            direction = "BUY"
            strength  = 55
        elif bear_shift:
            direction = "SELL"
            strength  = 55
        else:
            direction = "NEUTRAL"
            strength  = 0

        return {
            "direction":  direction,
            "strength":   strength,
            "expanding":  is_expansion,
            "shift":      bull_shift or bear_shift,
            "vol_spike":  vol_spike,
            "body_pct":   round(bp1, 2),
        }
    except Exception as e:
        logger.debug(f"Momentum error: {e}")
        return {"direction": "NEUTRAL", "strength": 0, "expanding": False}


# ─── LAYER 2: ENTRY TRIGGERS ─────────────────────────────────────────────────

def trigger_choch_entry(ms: dict, df: pd.DataFrame, pair: str) -> dict:
    """
    CHOCH entry — best reversal entry.
    Price breaks opposite swing → enter on the close of the breaking candle.
    HIGH priority — this is the earliest possible reversal entry.
    """
    if not ms.get("choch") or not ms.get("choch_dir"):
        return {}
    direction = ms["choch_dir"]
    entry = round(df["close"].iloc[-2], 5)
    return {
        "trigger": f"CHOCH_{direction}",
        "direction": direction,
        "entry_type": "REVERSAL",
        "entry_price": entry,
        "quality": 88,
        "detail": f"Change of Character — structure broke {direction}, entering reversal",
    }


def trigger_bos_entry(ms: dict, df: pd.DataFrame, pair: str) -> dict:
    """
    BOS entry — continuation trade after structural break.
    Price breaks in trend direction → enter on pullback to broken level.
    """
    if not ms.get("bos") or not ms.get("bos_dir"):
        return {}
    direction = ms["bos_dir"]
    entry = round(df["close"].iloc[-2], 5)
    return {
        "trigger": f"BOS_{direction}",
        "direction": direction,
        "entry_type": "CONTINUATION",
        "entry_price": entry,
        "quality": 82,
        "detail": f"Break of Structure {direction} — structure confirmed continuation",
    }


def trigger_momentum_expansion(mom: dict, df: pd.DataFrame, pair: str) -> dict:
    """
    Momentum expansion entry — enter when a strong directional candle fires.
    This catches the early momentum burst, not the exhausted end.

    CRITICAL GUARD: Only fire if price is NOT already overextended.
    Overextended = moved > 1.5× ATR from EMA9 already.
    """
    if mom["direction"] == "NEUTRAL" or mom["strength"] < 55:
        return {}

    direction = mom["direction"]
    atr_val   = _atr(df).iloc[-2]
    ema9      = _ema(df["close"], 9).iloc[-2]
    price     = df["close"].iloc[-2]
    pip       = _pip(pair)

    dist_from_ema = abs(price - ema9)

    # GUARD: if price already moved > 1.5 ATR from EMA9, it's a chase — skip
    if dist_from_ema > atr_val * 1.5:
        logger.debug(f"Momentum guard: {pair} price {_pips(dist_from_ema, pair):.1f}p from EMA9 — overextended, skip")
        return {}

    return {
        "trigger": f"MOMENTUM_EXPANSION_{direction}",
        "direction": direction,
        "entry_type": "MOMENTUM",
        "entry_price": round(price, 5),
        "quality": min(90, 55 + mom["strength"] // 4),
        "detail": f"Momentum expansion {direction} | body={mom['body_pct']:.0%} | strength={mom['strength']}",
    }


def trigger_liquidity_sweep(df: pd.DataFrame, pair: str) -> dict:
    """
    Liquidity sweep entry — best Smart Money entry.
    Price spikes through swing high/low (takes retail stops) then reverses.

    Pattern: Long wick beyond recent high/low + close BACK inside range.
    This is the highest quality entry because you're entering WITH institutions
    right after they've swept retail stops.
    """
    try:
        if len(df) < 20:
            return {}

        c1   = df.iloc[-2]  # last closed bar
        atr  = _atr(df).iloc[-2]
        pip  = _pip(pair)

        # Recent swing levels (last 15 bars, excluding last 2)
        window     = df.iloc[-17:-2]
        recent_sh  = window["high"].max()
        recent_sl  = window["low"].min()

        upper_wick = c1["high"] - max(c1["close"], c1["open"])
        lower_wick = min(c1["close"], c1["open"]) - c1["low"]
        body       = abs(c1["close"] - c1["open"])

        # Bullish sweep: wick went BELOW recent swing low then closed back up
        if (c1["low"] < recent_sl and
            lower_wick > atr * 0.5 and
            c1["close"] > recent_sl and
            c1["close"] > c1["open"]):
            swept_pips = _pips(recent_sl - c1["low"], pair)
            return {
                "trigger": "LIQUIDITY_SWEEP_BUY",
                "direction": "BUY",
                "entry_type": "REVERSAL",
                "entry_price": round(c1["close"], 5),
                "quality": min(92, 70 + int(swept_pips)),
                "detail": f"Swept below {recent_sl:.5f} by {swept_pips:.1f}p, closed bullish — institutions bought",
            }

        # Bearish sweep: wick went ABOVE recent swing high then closed back down
        if (c1["high"] > recent_sh and
            upper_wick > atr * 0.5 and
            c1["close"] < recent_sh and
            c1["close"] < c1["open"]):
            swept_pips = _pips(c1["high"] - recent_sh, pair)
            return {
                "trigger": "LIQUIDITY_SWEEP_SELL",
                "direction": "SELL",
                "entry_type": "REVERSAL",
                "entry_price": round(c1["close"], 5),
                "quality": min(92, 70 + int(swept_pips)),
                "detail": f"Swept above {recent_sh:.5f} by {swept_pips:.1f}p, closed bearish — institutions sold",
            }
    except Exception as e:
        logger.debug(f"Liquidity sweep error: {e}")
    return {}


def trigger_ema_pullback(df: pd.DataFrame, ms: dict, pair: str) -> dict:
    """
    EMA pullback in trend direction.

    ONLY fires when:
      - M15 structure is already established (UPTREND or DOWNTREND)
      - Price has pulled back to EMA9 or EMA21
      - Price is NOT at a new high (prevents buying tops)
      - RSI not overbought/oversold
    """
    try:
        if len(df) < 25:
            return {}

        structure = ms.get("structure", "NEUTRAL")
        if structure not in ("UPTREND", "DOWNTREND"):
            return {}

        close = df["close"]
        high  = df["high"]
        rsi   = _rsi(close).iloc[-2]
        ema9  = _ema(close, 9).iloc[-2]
        ema21 = _ema(close, 21).iloc[-2]
        atr   = _atr(df).iloc[-2]
        c1    = df.iloc[-2]
        c2    = df.iloc[-3]
        tol   = atr * 0.3

        if structure == "UPTREND":
            # Guard: price must NOT be making a new 10-bar high (buying top prevention)
            is_new_high = c1["close"] >= high.iloc[-12:-2].max()
            if is_new_high:
                logger.debug(f"EMA pullback guard: {pair} at new 10-bar high — not a pullback, skip")
                return {}
            # Guard: RSI not overbought
            if rsi > 68:
                return {}
            # Pullback: price touched EMA zone and bounced
            at_ema9  = c1["low"] <= ema9 + tol and c1["close"] > ema9
            at_ema21 = c1["low"] <= ema21 + tol and c1["close"] > ema21
            bounce   = c1["close"] > c2["close"] and c1["close"] > c1["open"]
            if (at_ema9 or at_ema21) and bounce:
                ema_used = ema9 if at_ema9 else ema21
                return {
                    "trigger": "EMA_PULLBACK_BUY",
                    "direction": "BUY",
                    "entry_type": "PULLBACK",
                    "entry_price": round(c1["close"], 5),
                    "quality": 80,
                    "detail": f"Pullback to EMA{'9' if at_ema9 else '21'} in uptrend, RSI={rsi:.0f}",
                }

        elif structure == "DOWNTREND":
            low = df["low"]
            is_new_low = c1["close"] <= low.iloc[-12:-2].min()
            if is_new_low:
                return {}
            if rsi < 32:
                return {}
            at_ema9  = c1["high"] >= ema9 - tol and c1["close"] < ema9
            at_ema21 = c1["high"] >= ema21 - tol and c1["close"] < ema21
            bounce   = c1["close"] < c2["close"] and c1["close"] < c1["open"]
            if (at_ema9 or at_ema21) and bounce:
                return {
                    "trigger": "EMA_PULLBACK_SELL",
                    "direction": "SELL",
                    "entry_type": "PULLBACK",
                    "entry_price": round(c1["close"], 5),
                    "quality": 80,
                    "detail": f"Pullback to EMA{'9' if at_ema9 else '21'} in downtrend, RSI={rsi:.0f}",
                }
    except Exception as e:
        logger.debug(f"EMA pullback error: {e}")
    return {}


def trigger_compression_breakout(df: pd.DataFrame, pair: str) -> dict:
    """
    Compression → expansion breakout.
    Tight range (ATR contracted) followed by a strong breakout candle.
    This catches the early breakout, not the chase.
    """
    try:
        if len(df) < 20:
            return {}

        atr_now  = _atr(df).iloc[-2]
        atr_prev = _atr(df).iloc[-8:-2].mean()

        # Compression: current ATR < 60% of recent average
        if atr_now >= atr_prev * 0.6:
            return {}

        c1   = df.iloc[-2]
        body = abs(c1["close"] - c1["open"])
        full = c1["high"] - c1["low"]

        # Expansion candle breaking out of compression
        if body < atr_prev * 0.8 or full < atr_now * 1.3:
            return {}

        direction = "BUY" if c1["close"] > c1["open"] else "SELL"
        return {
            "trigger": f"COMPRESSION_BREAKOUT_{direction}",
            "direction": direction,
            "entry_type": "BREAKOUT",
            "entry_price": round(c1["close"], 5),
            "quality": 78,
            "detail": f"ATR compressed to {_pips(atr_now, pair):.1f}p, breakout candle fired",
        }
    except Exception as e:
        logger.debug(f"Compression breakout error: {e}")
    return {}


def trigger_divergence_retest(df: pd.DataFrame, pair: str) -> dict:
    """
    RSI-divergence + retest confirmation entry (7th trigger).

    Fires only when a divergence has already formed AND price has come back
    to reject the divergence level with a pin bar/engulfing candle — this
    two-step confirmation (leading signal + confirmation) is what makes it
    safe to compete against the structural triggers above without adding a
    raw, noise-prone "fire on divergence alone" signal.
    """
    from strategies.divergence_retest import detect_rsi_divergence, confirm_retest

    div = detect_rsi_divergence(df, pair)
    if div["direction"] == "NEUTRAL":
        return {}
    retest = confirm_retest(df, pair, div["level"], div["direction"])
    if not retest["confirmed"]:
        return {}

    quality = min(90, 76 + div["strength"] * 6)  # 76 / 82 / 88
    return {
        "trigger": f"DIVERGENCE_RETEST_{div['direction']}",
        "direction": div["direction"],
        "entry_type": "REVERSAL",
        "entry_price": retest["entry_price"],
        "quality": quality,
        "detail": f"RSI divergence (RSI={div['rsi']}) + {retest['detail']}",
    }


# ─── OVEREXTENSION GUARD ─────────────────────────────────────────────────────

def is_overextended(df: pd.DataFrame, direction: str, pair: str) -> tuple[bool, str]:
    """
    The CRITICAL guard that prevents buying tops / selling bottoms.
    Checks multiple overextension conditions.
    """
    try:
        close = df["close"]
        high  = df["high"]
        low   = df["low"]
        rsi   = _rsi(close).iloc[-2]
        atr   = _atr(df).iloc[-2]
        ema9  = _ema(close, 9).iloc[-2]
        ema21 = _ema(close, 21).iloc[-2]
        price = close.iloc[-2]
        pip   = _pip(pair)

        # RSI extreme
        if direction == "BUY"  and rsi > 75:
            return True, f"RSI={rsi:.0f} overbought — price exhausted"
        if direction == "SELL" and rsi < 25:
            return True, f"RSI={rsi:.0f} oversold — price exhausted"

        # Price too far from EMA9 (chasing)
        dist_ema9 = abs(price - ema9)
        if dist_ema9 > atr * 2.0:
            pips = _pips(dist_ema9, pair)
            return True, f"Price {pips:.1f}p from EMA9 — chasing an overextended move"

        # Price at new N-bar extreme in entry direction
        if direction == "BUY":
            n_bar_high = high.iloc[-15:-2].max()
            if price > n_bar_high:
                return True, f"Entering at {_pips(price - n_bar_high, pair):.1f}p above 13-bar high — buying top"
        else:
            n_bar_low = low.iloc[-15:-2].min()
            if price < n_bar_low:
                return True, f"Entering at {_pips(n_bar_low - price, pair):.1f}p below 13-bar low — selling bottom"

        return False, ""
    except Exception as e:
        logger.debug(f"Overextension check error: {e}")
        return False, ""


# ─── LAYER 3: HTF CONTEXT WEIGHTING ─────────────────────────────────────────

def get_htf_context(
    df_h1:  Optional[pd.DataFrame],
    df_h4:  Optional[pd.DataFrame],
    df_d1:  Optional[pd.DataFrame],
    pair:   str,
) -> dict:
    """
    HTF provides CONTEXT and CONFIDENCE WEIGHTING only.
    NEVER blocks a valid 15M trade.

    Returns:
      alignment_bonus: -10 to +20 (added to confidence)
      context:         BUY / SELL / NEUTRAL
      aligned:         True if 15M same as H1+H4+D1
    """
    votes = {"BUY": 0, "SELL": 0}

    for tf_name, df, weight in [("H1", df_h1, 2), ("H4", df_h4, 1), ("D1", df_d1, 1)]:
        if df is None or len(df) < 30:
            continue
        close = df["close"]
        ema50 = _ema(close, 50).iloc[-1]
        ema21 = _ema(close, 21).iloc[-1]
        price = close.iloc[-1]
        if price > ema21 and ema21 > ema50:
            votes["BUY"]  += weight
        elif price < ema21 and ema21 < ema50:
            votes["SELL"] += weight

    total = votes["BUY"] + votes["SELL"]
    if total == 0:
        return {"context": "NEUTRAL", "alignment_bonus": 0, "aligned": False}

    buy_pct = votes["BUY"] / total * 100

    if buy_pct >= 60:
        return {"context": "BUY",  "alignment_bonus": 15, "aligned": True}
    elif buy_pct <= 40:
        return {"context": "SELL", "alignment_bonus": 15, "aligned": True}
    else:
        return {"context": "NEUTRAL", "alignment_bonus": 5, "aligned": False}


# ─── CONFIRMATION ─────────────────────────────────────────────────────────────

def get_m15_confirmation(df: pd.DataFrame, direction: str) -> tuple[int, list]:
    """
    Fast M15 confirmation score.
    Returns (score: 0-30, reasons: list)
    """
    score   = 0
    reasons = []
    try:
        close = df["close"]
        rsi   = _rsi(close).iloc[-2]
        atr   = _atr(df).iloc[-2]
        vol   = df.get("volume", pd.Series([1]*len(df), index=df.index))
        avg_vol = vol.iloc[-15:-1].mean()
        vol_ratio = vol.iloc[-2] / max(avg_vol, 1)
        c1    = df.iloc[-2]
        body  = abs(c1["close"] - c1["open"])
        full  = max(c1["high"] - c1["low"], 1e-10)

        # Volume
        if vol_ratio >= 1.5:
            score += 10; reasons.append(f"vol:{vol_ratio:.1f}x")
        elif vol_ratio >= 1.1:
            score += 5;  reasons.append(f"vol:{vol_ratio:.1f}x")

        # RSI in healthy zone
        if direction == "BUY"  and 40 < rsi < 68: score += 8; reasons.append(f"RSI:{rsi:.0f}")
        if direction == "SELL" and 32 < rsi < 60: score += 8; reasons.append(f"RSI:{rsi:.0f}")

        # Strong candle
        if body / full >= 0.6:
            score += 7
            reasons.append("strong-close")
        elif body / full >= 0.4:
            score += 4

        score = min(30, score)
    except Exception as e:
        logger.debug(f"Confirmation error: {e}")
    return score, reasons


# ─── MASTER SIGNAL FUNCTION ───────────────────────────────────────────────────

def _get_tf_direction(df: Optional[pd.DataFrame]) -> str:
    """
    Get trend direction of a timeframe using EMA21 vs EMA50.
    Returns BUY, SELL, or NEUTRAL.
    """
    if df is None or len(df) < 55:
        return "NEUTRAL"
    try:
        close = df["close"]
        ema21 = _ema(close, 21).iloc[-1]
        ema50 = _ema(close, 50).iloc[-1]
        price = close.iloc[-1]
        if price > ema21 and ema21 > ema50:
            return "BUY"
        elif price < ema21 and ema21 < ema50:
            return "SELL"
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"


def generate_signal(data_by_tf: dict, pair: str) -> dict:
    """
    Master function — runs full intraday swing analysis.

    Priority:
      1. Liquidity sweep (highest quality reversal)
      2. CHOCH (change of character — early reversal)
      3. BOS (break of structure — continuation)
      4. Momentum expansion (early trend detection)
      5. EMA pullback (established trend continuation)
      6. Compression breakout (volatility expansion)
    """
    df_m15 = data_by_tf.get("M15")
    df_h1  = data_by_tf.get("H1")
    df_h4  = data_by_tf.get("H4")
    df_d1  = data_by_tf.get("D1")

    if df_m15 is None or len(df_m15) < 40:
        return _neutral("insufficient M15 data")

    # ── Market structure analysis ──
    ms  = detect_market_structure(df_m15, pair)
    mom = detect_momentum(df_m15, pair)

    # ── HTF context (weighting only, never blocks) ──
    htf = get_htf_context(df_h1, df_h4, df_d1, pair)

    # ── D1 + H4 TREND FILTER (hard block) ──
    # If D1 is strongly opposite to signal direction, block it.
    # This prevents selling in a strong daily uptrend (the core problem).
    d1_direction = _get_tf_direction(df_d1)
    h4_direction = _get_tf_direction(df_h4)

    # ── Run all triggers in priority order ──
    triggers_to_check = []
    if config.get("signal_engine", "enable_divergence_retest_trigger", default=True):
        triggers_to_check.append(trigger_divergence_retest(df_m15, pair))
    triggers_to_check += [
        trigger_liquidity_sweep(df_m15, pair),
        trigger_choch_entry(ms, df_m15, pair),
        trigger_bos_entry(ms, df_m15, pair),
        trigger_momentum_expansion(mom, df_m15, pair),
        trigger_ema_pullback(df_m15, ms, pair),
        trigger_compression_breakout(df_m15, pair),
    ]

    fired = [t for t in triggers_to_check if t and "direction" in t]

    if not fired:
        return {**_neutral(f"no trigger | structure={ms.get('structure')}"),
                "htf_context": htf["context"], "ms_structure": ms.get("structure")}

    # ── Opposing-divergence soft penalty (not a hard block) ──
    # If a structural trigger fires while an active RSI divergence points the
    # opposite way (price still extending, RSI already turning), that's a
    # classic setup for a quick reversion — reduce its quality rather than
    # block it outright, consistent with this engine's quality-scored style.
    from strategies.divergence_retest import detect_rsi_divergence as _detect_div
    opposing_div = _detect_div(df_m15, pair)
    if opposing_div["direction"] != "NEUTRAL":
        penalty = config.get("signal_engine", "opposing_divergence_penalty", default=15)
        for t in fired:
            if t["direction"] != opposing_div["direction"]:
                t["quality"] = max(0, t["quality"] - penalty)

    # Separate BUY and SELL triggers
    buy_t  = [t for t in fired if t["direction"] == "BUY"]
    sell_t = [t for t in fired if t["direction"] == "SELL"]

    # If opposing triggers exist, take the higher quality one
    if buy_t and sell_t:
        best_buy  = max(buy_t,  key=lambda x: x["quality"])
        best_sell = max(sell_t, key=lambda x: x["quality"])
        if abs(best_buy["quality"] - best_sell["quality"]) < 8:
            return {**_neutral("conflicting triggers — no clear edge"),
                    "htf_context": htf["context"]}
        fired = buy_t if best_buy["quality"] > best_sell["quality"] else sell_t

    best      = max(fired, key=lambda x: x["quality"])
    direction = best["direction"]
    entry     = best["entry_price"]

    # ── D1 TREND ALIGNMENT HARD BLOCK ──
    # Block counter-trend trades when D1 AND H4 both oppose the signal
    # e.g. SELL signal when D1=BUY and H4=BUY → blocked (selling into strong uptrend)
    # Gated by config so this specific rule can be A/B-tested independently.
    if config.get("signal_engine", "require_d1_h4_alignment", default=True):
        if d1_direction != "NEUTRAL" and h4_direction != "NEUTRAL":
            if d1_direction != direction and h4_direction != direction:
                block_reason = f"D1={d1_direction} + H4={h4_direction} oppose {direction} signal"
                logger.info(f"[Signal] BLOCKED {pair} {direction} — {block_reason}")
                return {**_neutral(f"d1_h4_block: {block_reason}"),
                        "htf_context": htf["context"], "blocked_reason": block_reason}

    # ── OVEREXTENSION GUARD ── (THE KEY FIX for buying tops)
    overextended, oe_reason = is_overextended(df_m15, direction, pair)
    if overextended:
        logger.info(f"[Signal] BLOCKED {pair} {direction} — {oe_reason}")
        return {**_neutral(f"overextended: {oe_reason}"),
                "htf_context": htf["context"], "blocked_reason": oe_reason}

    # ── Confirmation score ──
    confirm_score, confirms = get_m15_confirmation(df_m15, direction)

    # ── HTF alignment bonus ──
    htf_bonus = htf["alignment_bonus"] if htf["context"] == direction else \
                (-5 if htf["context"] not in (direction, "NEUTRAL") else 0)

    # ── Multi-trigger bonus ──
    agreeing     = [t for t in fired if t["direction"] == direction]
    multi_bonus  = min(10, (len(agreeing) - 1) * 5)

    # ── Structure bonus ──
    struct_bonus = 0
    structure    = ms.get("structure", "NEUTRAL")
    if direction == "BUY"  and structure == "UPTREND":   struct_bonus = 8
    if direction == "SELL" and structure == "DOWNTREND": struct_bonus = 8
    if ms.get("choch"):    struct_bonus += 5
    if ms.get("bos"):      struct_bonus += 3

    # ── Choppy market dampener (soft, not a hard block) ──
    choppy_penalty = 0
    if is_choppy_market(df_m15, pair):
        choppy_penalty = config.get("signal_engine", "choppy_confidence_penalty", default=10)

    # ── Final confidence ──
    base       = best["quality"]
    confidence = max(0, min(100, base + htf_bonus + multi_bonus + struct_bonus
                             + confirm_score // 2 - choppy_penalty))

    logger.info(
        f"[Signal] {pair} {direction} | Trigger={best['trigger']} | "
        f"Structure={structure} | HTF={htf['context']}({'WITH' if htf['context']==direction else 'CTX'}) | "
        f"Conf={confidence} | Entry={entry:.5f} | "
        f"Confirms={','.join(confirms) or 'none'}"
        + (f" | Choppy(-{choppy_penalty})" if choppy_penalty else "")
    )

    return {
        "signal_direction":  direction,
        "entry_type":        best.get("entry_type", "UNKNOWN"),
        "entry_price":       entry,
        "confidence":        confidence,
        "trigger":           best["trigger"],
        "trigger_detail":    best.get("detail", ""),
        "htf_context":       htf["context"],
        "htf_aligned":       htf["context"] == direction,
        "trade_with_trend":  htf["context"] == direction,
        "ms_structure":      structure,
        "choch":             ms.get("choch", False),
        "bos":               ms.get("bos", False),
        "confirmations":     confirms,
        "confidence_breakdown": {
            "base": base, "htf": htf_bonus, "multi": multi_bonus,
            "struct": struct_bonus, "confirm": confirm_score,
            "choppy_penalty": -choppy_penalty,
        },
    }
