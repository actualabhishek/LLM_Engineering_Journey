"""
risk_management/risk_engine.py
------------------------------
Comprehensive risk management system.

Responsibilities:
  - Position sizing (fixed + ATR-adjusted)
  - Daily drawdown protection
  - Max concurrent trade enforcement
  - SL/TP calculation with spread adjustment
  - Break-even logic
  - Partial close logic
  - Trailing SL calculation
  - Trade cooldown enforcement

ALL calculations are deterministic.
No LLM dependency here — risk is not negotiable.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple

from core.config_manager import config
from core.state_manager import get_daily_stats, count_active_trades
from core.logger import get_logger
from strategies.indicators import get_pip_value

logger = get_logger(__name__)

# Spread cost in USD at 0.1 lot (approximate, varies by pair/broker).
# Only used as a fallback when live MT5 tick data isn't available
# (mt5_engine.get_pip_value_usd_per_lot() is preferred — see Phase 6).
# Live pairs: EURUSD, GBPUSD. Others kept dormant for future re-expansion.
SPREAD_USD_PER_PIP_01_LOT = {
    "EURUSD": 1.0, "GBPUSD": 1.0,
    # dormant:
    "AUDUSD": 0.72, "USDCAD": 0.74, "USDJPY": 0.91, "EURJPY": 0.91, "GBPJPY": 0.91,
    # XAUUSD (gold): confirmed via live MT5 symbol_info on this account —
    # tick_value=$1.00, tick_size=0.01, contract_size=100oz -> $1/pip/lot,
    # i.e. 10x SMALLER than a forex major's ~$10/pip/lot. Without this entry
    # the dict's default (1.0 -> $10/pip/lot) would silently under-risk gold
    # trades by ~10x relative to the intended risk_pct.
    "XAUUSD": 0.1,
}


class RiskEngine:
    """
    All risk calculations in one place.
    Methods are pure functions (stateless) except drawdown check.
    """

    def can_take_trade(self, pair: str, direction: str) -> Tuple[bool, str]:
        """
        Master pre-trade risk gate.
        Returns (allowed: bool, reason: str).
        """
        # Kill switch
        from core.state_manager import is_kill_switch_active
        if is_kill_switch_active():
            return False, "Kill switch is active"

        # Daily drawdown
        stats = get_daily_stats()
        if stats["current_drawdown_pct"] >= config.max_daily_drawdown_pct:
            return False, f"Daily drawdown limit reached ({stats['current_drawdown_pct']:.1f}%)"

        # Weekly drawdown (simplified: use same file)
        if stats["net_pnl"] < 0:
            weekly_loss_pct = abs(stats["net_pnl"]) / max(stats.get("peak_balance", 10000), 1) * 100
            if weekly_loss_pct >= config.get("risk", "max_weekly_drawdown_pct"):
                return False, f"Weekly loss limit reached"

        # Max concurrent trades
        active = count_active_trades()
        if active >= config.max_concurrent_trades:
            return False, f"Max concurrent trades ({config.max_concurrent_trades}) reached"

        # Max daily trades
        if stats["trades_taken"] >= config.get("trading", "max_trades_per_day"):
            return False, f"Max daily trades ({config.get('trading', 'max_trades_per_day')}) reached"

        # Improvement #7: Score-based cooldown — high conviction setups get shorter cooldown
        base_cooldown   = config.get("trading", "trade_cooldown_minutes") or 30
        high_cooldown   = config.get("trading", "trade_cooldown_high_score_minutes") or 15
        high_threshold  = config.get("trading", "cooldown_high_score_threshold") or 85
        # We don't have score here directly, but we can check last trade confidence from state
        by_pair = stats.get("last_trade_time_by_pair", {})
        pair_last = by_pair.get(pair) or stats.get("last_trade_time")
        if pair_last:
            try:
                last_dt = datetime.fromisoformat(pair_last)
                elapsed_secs = (datetime.now(timezone.utc) - last_dt).total_seconds()
                # Use shorter cooldown if last trade on this pair was high confidence
                last_score = stats.get("last_trade_score_by_pair", {}).get(pair, 70)
                cooldown = high_cooldown if last_score >= high_threshold else base_cooldown
                cooldown_secs = cooldown * 60
                if elapsed_secs < cooldown_secs:
                    remaining_secs = cooldown_secs - elapsed_secs
                    remaining_mins = max(1, int(remaining_secs / 60))
                    return False, f"Cooldown on {pair}: {remaining_mins}min remaining"
            except Exception:
                pass

        # Same pair already open
        from core.state_manager import get_active_trades
        active_trades = get_active_trades()
        for t in active_trades.values():
            if t.get("pair") == pair:
                return False, f"Position already open on {pair}"

        # Currency correlation guard
        # Prevents opening two trades that share the same base/quote currency
        # in the same direction (correlated risk = like one big trade)
        corr_blocked, corr_reason = self._check_currency_correlation(
            pair, direction, active_trades
        )
        if corr_blocked:
            return False, corr_reason

        return True, "Risk checks passed"

    def _check_currency_correlation(
        self,
        pair: str,
        direction: str,
        active_trades: dict,
    ) -> tuple:
        """
        Prevents logically contradictory and correlated USD positions.

        KEY INSIGHT:
          EURUSD SELL = buying USD (USD strengthening view)
          USDJPY SELL = selling USD (USD weakening view)
          → These are CONTRADICTORY — can't hold both simultaneously.
          → If you don't know if USD is going up or down, don't trade it.

        RULE: Only ONE USD directional view allowed at a time.
          Any two USD-involved trades must agree on USD direction.

        USD direction mapping:
          EURUSD BUY  → SHORT USD (bearish USD)
          EURUSD SELL → LONG USD  (bullish USD)
          GBPUSD BUY  → SHORT USD
          GBPUSD SELL → LONG USD
          AUDUSD BUY  → SHORT USD
          AUDUSD SELL → LONG USD
          USDJPY BUY  → LONG USD  (bullish USD)
          USDJPY SELL → SHORT USD (bearish USD)
          USDCAD BUY  → LONG USD
          USDCAD SELL → SHORT USD

        Examples:
          EURUSD SELL (LONG) + GBPUSD SELL (LONG) → SAME → BLOCK (double exposure)
          EURUSD SELL (LONG) + USDJPY SELL (SHORT) → CONTRADICTORY → BLOCK
          EURUSD SELL (LONG) + USDJPY BUY  (LONG)  → SAME → BLOCK (double exposure)
          EURJPY + GBPJPY → no USD → check base currency only
        """
        pair = pair.upper()

        def get_usd_view(p, d):
            """Returns LONG_USD, SHORT_USD, or None if no USD involved."""
            if "USD" not in p:
                return None
            if p.startswith("USD"):  # USDXXX: BUY=buy USD=LONG, SELL=sell USD=SHORT
                return "LONG_USD" if d == "BUY" else "SHORT_USD"
            else:                    # XXXUSD: BUY=sell USD=SHORT, SELL=buy USD=LONG
                return "SHORT_USD" if d == "BUY" else "LONG_USD"

        def get_base(p):
            p = p.upper()
            return p[:3] if len(p) == 6 else None

        new_usd_view = get_usd_view(pair, direction)
        new_base     = get_base(pair)

        for t in active_trades.values():
            t_pair = t.get("pair", "").upper()
            t_dir  = t.get("direction", "")
            t_usd_view = get_usd_view(t_pair, t_dir)
            t_base     = get_base(t_pair)

            # Block ANY conflicting USD view — same OR opposite
            # Both cases mean the bot has no clear USD conviction
            if new_usd_view and t_usd_view:
                if new_usd_view != t_usd_view:
                    return True, (
                        f"Contradictory USD view: {pair} {direction} says {new_usd_view} "
                        f"but {t_pair} {t_dir} says {t_usd_view} — no clear USD direction"
                    )
                else:
                    return True, (
                        f"Duplicate USD exposure: {pair} {direction} ({new_usd_view}) "
                        f"already have {t_pair} {t_dir} ({t_usd_view})"
                    )

            # Block same non-USD base in same direction (EURJPY + EURUSD both SELL)
            if new_base and t_base and new_base == t_base and direction == t_dir and new_base != "USD":
                return True, (
                    f"Correlated: both {direction} on {new_base} "
                    f"({pair} + {t_pair})"
                )

        return False, ""

    def calculate_position_size(
        self,
        account_balance: float,
        sl_pips: float,
        pair: str,
        confidence_score: float = 75.0,
        pip_usd_per_lot: Optional[float] = None,
        free_margin: Optional[float] = None,
        margin_usd_per_lot: Optional[float] = None,
    ) -> float:
        """
        Risk-based position sizing.
        Lot size scales with account equity/balance and confidence score.

        Formula: lots = (balance × risk_pct) / (sl_pips × pip_value_per_lot)

        Risk tiers:
          Score 85+  → 1.5% risk (high conviction)
          Score 75+  → 1.0% risk (standard)
          Score <75  → 0.5% risk (cautious)

        `pip_usd_per_lot` / `margin_usd_per_lot`: optionally pass live values
        from mt5_engine (real broker tick value/contract size) instead of the
        static SPREAD_USD_PER_PIP_01_LOT approximation. Both are optional so
        this stays pure/deterministic for the backtester and simulation mode.

        `free_margin`: when provided (live-trading only), the result is
        clamped so it can never exceed what account margin actually allows —
        a pure safety cap, never increases the risk-based lot size.
        """
        min_lot = config.get("risk", "min_lot_size") or 0.01
        max_lot = config.get("risk", "max_lot_size") or 0.20

        if account_balance <= 0 or sl_pips <= 0:
            return min_lot

        # Select risk % based on confidence score
        score_high = config.get("risk", "score_high_threshold") or 85
        score_caut = config.get("risk", "score_cautious_threshold") or 74

        if confidence_score >= score_high:
            risk_pct = (config.get("risk", "risk_pct_high") or 1.5) / 100
        elif confidence_score >= score_caut:
            risk_pct = (config.get("risk", "risk_pct_standard") or 1.0) / 100
        else:
            risk_pct = (config.get("risk", "risk_pct_cautious") or 0.5) / 100

        # Dollar risk for this trade
        risk_usd = account_balance * risk_pct

        # Pip value per lot (USD per pip per 1.0 standard lot) — prefer live
        # broker data when supplied, fall back to the static approximation.
        pip_usd_per_lot = pip_usd_per_lot or (SPREAD_USD_PER_PIP_01_LOT.get(pair, 1.0) * 10)

        # Lot calculation
        raw_lots = risk_usd / (sl_pips * pip_usd_per_lot)

        # Clamp and round
        lot_size = max(min_lot, min(max_lot, raw_lots))

        # Margin sanity clamp — can only reduce lot size vs. the risk-based
        # calculation above, never increase it.
        if free_margin and margin_usd_per_lot and margin_usd_per_lot > 0:
            safety_factor = config.get("risk", "margin_safety_factor", default=0.8)
            max_lot_by_margin = (free_margin * safety_factor) / margin_usd_per_lot
            if max_lot_by_margin < lot_size:
                logger.warning(
                    f"Position size {pair}: margin clamp reduced lot "
                    f"{lot_size:.2f} -> {max(min_lot, max_lot_by_margin):.2f} "
                    f"(free_margin=${free_margin:.0f})"
                )
                lot_size = max(min_lot, max_lot_by_margin)

        lot_size = round(lot_size, 2)

        logger.debug(
            f"Position size {pair}: balance=${account_balance:.0f} "
            f"risk={risk_pct*100:.1f}% score={confidence_score:.0f} "
            f"sl={sl_pips:.0f}p → {lot_size} lots (${risk_usd:.2f} at risk)"
        )
        return lot_size

    def calculate_sl_tp(
        self,
        pair: str,
        direction: str,
        entry_price: float,
        atr_pips: float,
        spread_pips: float = 1.5,
        confidence_score: float = 70.0,
        session: str = "london",
    ) -> Tuple[float, float]:
        """
        Calculate SL and TP prices.
        Improvement #5: Score-based TP multiplier
        Improvement #6: Session TP extension
        """
        pip = get_pip_value(pair)
        sl_mult = config.get("risk", "atr_sl_multiplier")

        # #5: Select TP multiplier based on confidence score
        score_high = config.get("risk", "score_high_threshold") or 85
        score_caut  = config.get("risk", "score_cautious_threshold") or 74
        if confidence_score >= score_high:
            tp_mult = config.get("risk", "atr_tp_multiplier_high") or 4.0
            logger.debug(f"High score {confidence_score:.0f} → TP at {tp_mult}R")
        elif confidence_score <= score_caut:
            tp_mult = config.get("risk", "atr_tp_multiplier_cautious") or 2.0
            logger.debug(f"Cautious score {confidence_score:.0f} → TP at {tp_mult}R")
        else:
            tp_mult = config.get("risk", "atr_tp_multiplier") or 3.0

        # #6: Session TP extension for London/NY open
        bonus_sessions = ("london_open", "lon_open", "ny_open", "overlap")
        if any(s in session.lower() for s in bonus_sessions):
            bonus_pct = (config.get("risk", "tp_session_bonus_pct") or 0) / 100
            tp_mult = round(tp_mult * (1 + bonus_pct), 2)
            logger.debug(f"Session bonus → TP extended to {tp_mult}R")

        # Minimum SL distance to guarantee at least 1.5 RR after spread
        # Work backwards: need SL >= spread / (tp_mult - 1.5) at minimum
        min_sl_pips = 10.0 if "JPY" in pair.upper() else 8.0
        # Also ensure TP covers spread cost to still get 1.5 RR
        # sl_pips * tp_mult - spread >= sl_pips * 1.5
        # sl_pips >= spread / (tp_mult - 1.5)
        if tp_mult > 1.5:
            min_sl_from_rr = spread_pips / (tp_mult - 1.5) + 1.0
        else:
            min_sl_from_rr = spread_pips * 3  # fallback
        min_sl_pips = max(min_sl_pips, min_sl_from_rr)
        effective_atr_pips = max(atr_pips, min_sl_pips / sl_mult)

        sl_distance = effective_atr_pips * sl_mult * pip
        tp_distance = effective_atr_pips * tp_mult * pip
        spread_adj  = spread_pips * pip * 0.5

        if direction == "BUY":
            sl = round(entry_price - sl_distance - spread_adj, 5)
            tp = round(entry_price + tp_distance, 5)
        else:
            sl = round(entry_price + sl_distance + spread_adj, 5)
            tp = round(entry_price - tp_distance, 5)

        return sl, tp

    def calculate_breakeven(
        self,
        pair: str,
        direction: str,
        open_price: float,
        spread_pips: float = 1.5,
    ) -> float:
        """
        Move SL to break-even (+spread to cover costs).
        """
        pip = get_pip_value(pair)
        spread_adj = spread_pips * pip

        if direction == "BUY":
            return round(open_price + spread_adj, 5)
        else:
            return round(open_price - spread_adj, 5)

    def should_move_to_breakeven(
        self,
        direction: str,
        open_price: float,
        current_price: float,
        tp_price: float,
        current_sl: float,
    ) -> Tuple[bool, Optional[float]]:
        """
        Return (should_move: bool, new_sl: float|None).
        Triggers when price reaches 1:1 RR from open.
        """
        # #3: Earlier breakeven — trigger at 0.7R instead of 1.0R
        be_trigger_rr = config.get("risk", "breakeven_trigger_rr") or 0.7
        sl_distance   = abs(open_price - current_sl)
        trigger_distance = sl_distance * be_trigger_rr  # fraction of SL distance

        if direction == "BUY":
            if current_price >= open_price + trigger_distance:
                be_sl = round(open_price + sl_distance * 0.05, 5)  # 5% of SL distance above entry
                if current_sl < be_sl:
                    return True, be_sl
        else:
            if current_price <= open_price - trigger_distance:
                be_sl = round(open_price - sl_distance * 0.05, 5)
                if current_sl > be_sl:
                    return True, be_sl

        return False, None

    def calculate_trailing_sl(
        self,
        pair: str,
        direction: str,
        current_price: float,
        current_sl: float,
        atr_pips: float,
        open_price: float = 0.0,
    ) -> Optional[float]:
        """
        Calculate new trailing SL position.
        Returns new SL if it should be moved, else None.
        Uses ATR-based trailing distance.
        """
        pip = get_pip_value(pair)

        # #2: Tighter trailing after 2R — lock in more profit
        tight_after_rr = config.get("risk", "trail_sl_tight_after_rr") or 2.0
        normal_mult    = config.get("risk", "trail_sl_atr_multiplier")  or 1.5
        tight_mult     = config.get("risk", "trail_sl_tight_multiplier") or 0.8

        # Estimate how far price has moved in R multiples
        sl_dist = abs(open_price - current_sl) if open_price > 0 else atr_pips * pip
        price_move = abs(current_price - open_price)
        r_moved = price_move / sl_dist if sl_dist > 0 else 0

        trail_mult     = tight_mult if r_moved >= tight_after_rr else normal_mult
        trail_distance = atr_pips * trail_mult * pip

        if direction == "BUY":
            new_sl = round(current_price - trail_distance, 5)
            if new_sl > current_sl:
                return new_sl
        else:
            new_sl = round(current_price + trail_distance, 5)
            if new_sl < current_sl:
                return new_sl

        return None

    def should_partial_close(
        self,
        direction: str,
        open_price: float,
        current_price: float,
        tp_price: float,
        partial_done: bool,
        partial_2_done: bool = False,
        current_sl: float = 0.0,
    ) -> Tuple[bool, int]:
        """
        Improvement #4: Staged partial closes.
        Returns (should_close: bool, stage: int)
          stage 1 = first partial (33% at 1.0R)
          stage 2 = second partial (33% at 2.0R)
          stage 0 = no close

        Guards:
          - sl_dist must come from actual SL, not fallback
          - moved must be positive (price going our way)
          - minimum move of 0.5R before any partial allowed
        """
        # Must have real SL to calculate R multiples
        if not current_sl or not open_price:
            return False, 0

        sl_dist = abs(open_price - current_sl)
        if sl_dist <= 0:
            return False, 0

        # Directional move — must be positive (in our favour)
        if direction == "BUY":
            moved = current_price - open_price
        else:
            moved = open_price - current_price

        # If price moved against us, never partial close
        if moved <= 0:
            return False, 0

        r_moved = moved / sl_dist

        # Stage 2: second partial at 2.0R
        trigger_2 = config.get("risk", "partial_close_2_at_rr") or 2.0
        if not partial_2_done and partial_done and r_moved >= trigger_2:
            return True, 2

        # Stage 1: first partial at 1.0R (must be at least breakeven first)
        trigger_1 = config.get("risk", "partial_close_at_rr") or 1.0
        if not partial_done and r_moved >= trigger_1:
            return True, 1

        return False, 0

    def should_exit_by_time(
        self,
        open_time: str,
        max_hours: int = 24,
    ) -> bool:
        """
        Exit trade if it has been open too long without hitting target.
        Prevents overnight exposure on losing positions.
        """
        try:
            ot = datetime.fromisoformat(open_time)
            return (datetime.now(timezone.utc) - ot).total_seconds() > max_hours * 3600
        except Exception:
            return False

    def validate_rr(self, sl_pips: float, tp_pips: float) -> Tuple[bool, float]:
        """
        Validate Risk:Reward ratio meets minimum requirement.
        """
        if sl_pips <= 0:
            return False, 0.0
        rr = tp_pips / sl_pips
        min_rr = config.get("trading", "min_rr_ratio")
        # Small tolerance for floating point precision (1.499 treated as 1.5)
        return rr >= (min_rr - 0.05), round(rr, 2)


# Module-level singleton
risk_engine = RiskEngine()
