"""
trading_orchestrator.py
------------------------
Master trading orchestrator.
Coordinates all engines in the correct sequence.

Signal Processing Pipeline:
  1. Receive signal (from webhook or internal scanner)
  2. Fetch multi-timeframe data from MT5
  3. Calculate indicators on all timeframes
  4. Run MTF alignment analysis
  5. Calculate confidence score (deterministic)
  6. Check session filter
  7. Check news filter
  8. Check risk management rules
  9. AI decision (if needed)
  10. Execute trade if TAKE decision
  11. Log everything

Also contains the autonomous scanner (no TradingView required):
  - Scans all pairs on each new M15 candle
  - Generates its own signals
  - Follows the same pipeline
"""

import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from core.config_manager import config
from core.logger import get_logger
from core.session_manager import get_session_info, is_trading_time
from core.state_manager import is_kill_switch_active, get_daily_stats, update_drawdown
from mt5_execution.mt5_engine import mt5_engine
from mt5_execution.trade_monitor import trade_monitor
from strategies.multi_timeframe import mtf_analyzer
from strategies.confidence_engine import confidence_engine
from ai_engine.decision_engine import decision_engine
from risk_management.risk_engine import risk_engine
from news_engine.news_filter import news_filter
from strategies.advanced_analysis import run_advanced_analysis
from strategies.precision_entry import run_precision_checks
from strategies.early_entry import run_early_entry_analysis
from strategies.signal_engine import generate_signal

logger = get_logger(__name__)


class TradingOrchestrator:
    """
    Central intelligence coordinator.
    Thread-safe: multiple signals may arrive concurrently.
    """

    def __init__(self):
        self._processing_lock = threading.Lock()
        self._last_scan_candle: Dict[str, str] = {}  # pair -> last candle time

    # ============================================================
    # Signal Processing (from TradingView webhook)
    # ============================================================

    def process_signal(self, signal: Dict) -> None:
        """
        Process incoming TradingView signal.
        Full evaluation pipeline with all safety gates.
        """
        pair = signal.get("symbol")
        raw_signal = signal.get("signal")

        logger.info(f"Processing signal: {pair} {raw_signal}")

        # ---- Handle close signals immediately ----
        if raw_signal in ("CLOSE", "CLOSE_BUY", "CLOSE_SELL"):
            self._handle_close_signal(pair, raw_signal)
            return

        # ---- Entry signal processing ----
        with self._processing_lock:
            self._evaluate_and_execute(pair, raw_signal, tv_signal=signal)

    def _evaluate_and_execute(
        self,
        pair: str,
        direction: str,
        tv_signal: Optional[Dict] = None,
        signal: Optional[Dict] = None,
    ) -> None:
        """
        Full evaluation pipeline.
        Returns early at any gate failure (fast path out).
        """
        # Gate 1: Kill switch
        if is_kill_switch_active():
            logger.info(f"SKIP {pair}: Kill switch active")
            return

        # Gate 2: Session filter
        trading_ok, session_reason = is_trading_time()
        if not trading_ok:
            logger.info(f"SKIP {pair}: {session_reason}")
            return

        # Gate 2b: Daily flat-close cutover proximity — don't open a trade
        # that wouldn't get a fair chance before the strict same-day close.
        cutover_ok, cutover_reason = self._cutover_proximity_ok()
        if not cutover_ok:
            logger.info(f"SKIP {pair}: {cutover_reason}")
            return

        session_info = get_session_info()

        # Gate 3: Risk pre-check (fast)
        can_trade, risk_reason = risk_engine.can_take_trade(pair, direction)
        if not can_trade:
            logger.info(f"SKIP {pair}: {risk_reason}")
            return

        # Gate 4: News filter
        news_safe, news_reason = news_filter.is_safe_to_trade(pair)
        if not news_safe:
            logger.info(f"SKIP {pair}: {news_reason}")
            return

        news_context = news_filter.get_news_context(pair)

        # Gate 5: Get current symbol info (spread check)
        sym_info = mt5_engine.get_symbol_info(pair)
        if not sym_info:
            logger.warning(f"SKIP {pair}: Could not fetch symbol info")
            return

        spread_pips = sym_info.get("spread", 99)
        if spread_pips > config.get("risk", "spread_max_pips"):
            logger.info(f"SKIP {pair}: Spread {spread_pips} pips too wide")
            return

        # Gate 6: Fetch multi-timeframe data
        data_by_tf = {}
        for tf in ["M15", "H1", "H4", "D1"]:
            df = mt5_engine.get_candles(pair, tf, count=300)
            if df is not None:
                data_by_tf[tf] = df

        if "M15" not in data_by_tf:
            logger.warning(f"SKIP {pair}: No M15 data available")
            return

        # Gate 7: Multi-timeframe analysis
        mtf = mtf_analyzer.analyze(data_by_tf, pair)

        # Validate direction aligns with MTF consensus
        if mtf["direction"] != direction and mtf["aligned"]:
            logger.info(f"SKIP {pair}: Signal direction {direction} conflicts with MTF {mtf['direction']}")
            return

        # Gate 8a: Advanced pattern analysis (S/R, trendlines, chart patterns,
        #          order blocks, Fibonacci, candlestick patterns)
        adv = run_advanced_analysis(data_by_tf["M15"], pair)
        if adv["signal"] != "NEUTRAL" and adv["signal"] != direction:
            logger.info(
                f"SKIP {pair}: Advanced analysis ({adv['signal']}) "
                f"conflicts with signal direction ({direction})"
            )
            return
        if adv["patterns"]:
            logger.info(f"[Pattern] {adv['summary']}")

        # Gate 8b: AI decision engine (deterministic + optional LLM)
        decision = decision_engine.evaluate(
            pair=pair,
            signal_direction=direction,
            mtf_analysis=mtf,
            session_info=session_info,
            spread_pips=spread_pips,
            news_context=news_context,
            advanced_analysis=adv,
            signal_confidence=signal.get("confidence", 0) if signal else 0,
        )

        if decision["decision"] == "SKIP":
            logger.info(f"SKIP {pair}: {decision.get('recommendation')} | Score={decision['final_score']}")
            return

        # Gate 9: SL/TP calculation and RR validation
        m15_ind = mtf.get("m15_indicators") or {}
        atr_pips = m15_ind.get("atr_pips", 15.0)
        entry_price = sym_info["ask"] if direction == "BUY" else sym_info["bid"]

        sl, tp = risk_engine.calculate_sl_tp(
            pair, direction, entry_price, atr_pips, spread_pips,
            confidence_score=decision.get("final_score", 70),
            session=session_info.get("session", "london"),
        )

        sl_pips = abs(entry_price - sl) / config.get("indicators", "atr", "volatility_min_pips", default=0.0001) * 10
        tp_pips = abs(tp - entry_price) / config.get("indicators", "atr", "volatility_min_pips", default=0.0001) * 10

        # Use TradingView SL/TP if provided and valid
        if tv_signal and tv_signal.get("sl") and tv_signal.get("tp"):
            tv_sl, tv_tp = tv_signal["sl"], tv_signal["tp"]
            # Validate they make sense
            if direction == "BUY" and tv_sl < entry_price < tv_tp:
                sl, tp = tv_sl, tv_tp
            elif direction == "SELL" and tv_tp < entry_price < tv_sl:
                sl, tp = tv_sl, tv_tp

        # Recalculate pips for validation
        from strategies.indicators import get_pip_value
        pip = get_pip_value(pair)
        sl_pips = abs(entry_price - sl) / pip
        tp_pips = abs(tp - entry_price) / pip

        rr_ok, rr_ratio = risk_engine.validate_rr(sl_pips, tp_pips)
        if not rr_ok:
            logger.info(f"SKIP {pair}: RR {rr_ratio:.1f} below minimum {config.get('trading', 'min_rr_ratio')}")
            return

        # Gate 10: Position sizing — uses equity (not balance) so lot size
        # reacts in real time to floating P&L on other open positions,
        # consistent with the equity-based drawdown circuit breaker.
        account = mt5_engine.get_account_info()
        equity = account["equity"] if account else 10000.0
        lot_size = risk_engine.calculate_position_size(
            equity, sl_pips, pair, confidence_score=decision.get("final_score", 75),
            pip_usd_per_lot=mt5_engine.get_pip_value_usd_per_lot(pair),
            free_margin=account.get("margin_free") if account else None,
            margin_usd_per_lot=mt5_engine.get_margin_usd_per_lot(pair),
        )

        # Gate 10b: Precision entry checks (7 improvements)
        df_h1 = data_by_tf.get("H1")
        precision = run_precision_checks(
            direction=direction,
            pair=pair,
            current_price=entry_price,
            base_score=decision["final_score"],
            base_lot=lot_size,
            sl_pips=sl_pips,
            mtf_analysis=mtf,
            df_m15=data_by_tf["M15"],
            df_h1=df_h1,
            account_balance=equity,
            pattern_count=adv.get("pattern_count", 0),
            trigger_name=signal.get("trigger", "") if signal else "",
        )

        if not precision["allowed"]:
            # Only hard-block on session/divergence — NOT on HTF bias
            # HTF bias is context only per trading philosophy
            block = precision["block_reason"]
            if any(x in block for x in ("Dead zone", "Off-hours", "divergence")):
                logger.info(f"SKIP {pair}: [Precision] {block}")
                return
            else:
                logger.debug(f"[Precision] soft block ignored (HTF context only): {block}")

        if not precision["enter_now"]:
            logger.info(
                f"WAIT {pair}: {precision['block_reason'] or 'Pullback pending'} "
                f"| Ideal entry: {precision['ideal_entry']:.5f}"
            )
            return

        # Use precision-adjusted lot size and score
        lot_size    = precision["recommended_lots"]
        final_score = precision["adjusted_score"]

        # ── Early entry analysis ──────────────────────────────────
        # A confirmed DIVERGENCE_RETEST trigger already did the "wait for
        # the right moment" work — tell early-entry so it doesn't redundantly
        # re-delay or under-score an already-confirmed retest.
        divergence_ctx = (
            {"confirmed": True}
            if signal and str(signal.get("trigger", "")).startswith("DIVERGENCE_RETEST")
            else None
        )
        early = run_early_entry_analysis(
            df_m15=data_by_tf["M15"],
            direction=direction,
            current_price=entry_price,
            pair=pair,
            df_h1=data_by_tf.get("H1"),
            divergence_context=divergence_ctx,
        )

        # Apply early entry confidence bonus to final score
        final_score = min(100, final_score + early["confidence_bonus"])

        # If WAIT signal from early entry AND we're not in a strong setup,
        # skip this bar and wait for better entry next candle
        if early["entry_type"] == "WAIT" and final_score < 85:
            logger.info(
                f"WAIT {pair}: Early entry analysis suggests waiting — "
                f"{early['checks']['h1_momentum'].get('reason', '')} | "
                f"Will re-evaluate next candle"
            )
            return

        # Use optimal entry price if it's meaningfully better (>1 pip improvement)
        pip = 0.01 if "JPY" in pair.upper() else 0.0001
        price_improvement = abs(early["optimal_entry"] - entry_price) / pip
        if price_improvement >= 1.0 and early["entry_type"] == "IMMEDIATE":
            logger.info(
                f"[EarlyEntry] Better entry found: {entry_price:.5f} → "
                f"{early['optimal_entry']:.5f} (~{price_improvement:.1f}p better)"
            )
            entry_price = early["optimal_entry"]
            # Recalculate SL/TP from new entry price
            sl, tp = risk_engine.calculate_sl_tp(
                pair, direction, entry_price, atr_pips, spread_pips,
                confidence_score=final_score,
                session=session_info.get("session", "london"),
            )

        # ============================================================
        # EXECUTE TRADE
        # ============================================================
        logger.info(
            f"EXECUTING {pair} {direction} | Score={final_score:.0f} "
            f"| SL={sl} | TP={tp} | Lot={lot_size} | RR={rr_ratio:.1f} "
            f"| EntryQ={early['entry_quality']:.0f}"
        )

        trade = mt5_engine.open_trade(
            pair=pair,
            direction=direction,
            lot_size=lot_size,
            sl=sl,
            tp=tp,
            comment=f"AI:{final_score:.0f}",
            confidence=final_score,
        )

        if trade:
            logger.info(f"Trade executed successfully: {pair} {direction} #{trade.get('ticket')}")
        else:
            logger.error(f"Trade execution FAILED: {pair} {direction}")

    def _handle_close_signal(self, pair: str, signal_type: str) -> None:
        """Handle close signals from TradingView."""
        from core.state_manager import get_active_trades
        active = get_active_trades()

        for ticket_str, trade in list(active.items()):
            if trade["pair"] != pair:
                continue

            direction = trade["direction"]
            if signal_type == "CLOSE":
                mt5_engine.close_trade(int(ticket_str), reason="tv_close_signal")
            elif signal_type == "CLOSE_BUY" and direction == "BUY":
                mt5_engine.close_trade(int(ticket_str), reason="tv_close_buy")
            elif signal_type == "CLOSE_SELL" and direction == "SELL":
                mt5_engine.close_trade(int(ticket_str), reason="tv_close_sell")

    # ============================================================
    # Autonomous Scanner (no TradingView required)
    # ============================================================

    def start_autonomous_scanner(self) -> None:
        """
        Start the autonomous pair scanner.
        Scans all configured pairs every 5 minutes.
        Generates its own signals without TradingView dependency.
        """
        thread = threading.Thread(
            target=self._scanner_loop,
            name="AutonomousScanner",
            daemon=True
        )
        thread.start()
        logger.info("Autonomous scanner started")

    def _scanner_loop(self) -> None:
        """Scan all pairs and generate signals independently."""
        from datetime import datetime as _dt, timezone as _tz
        while True:
            try:
                for pair in config.pairs:
                    if is_kill_switch_active():
                        break
                    self._scan_pair(pair)
                    time.sleep(2)  # Stagger pair scans
            except Exception as e:
                logger.error(f"Scanner error: {e}", exc_info=True)
            logger.info(f"Scanner heartbeat | {_dt.now(_tz.utc).strftime('%H:%M')} UTC | waiting for next M15 candle")
            time.sleep(300)  # Scan every 5 minutes

    def _cutover_proximity_ok(self) -> tuple[bool, str]:
        """
        Block new entries too close to the daily flat-close cutover — a trade
        opened right before the cutover gets force-closed almost immediately
        regardless of P&L, so it never gets a fair chance to work.
        """
        cutover_str = config.get("risk", "flat_close_cutover_utc", default="21:00")
        min_minutes = config.get("risk", "min_minutes_before_cutover_for_new_trade", default=30)
        try:
            hh, mm = (int(x) for x in cutover_str.split(":"))
        except Exception:
            hh, mm = 21, 0
        now = datetime.now(timezone.utc)
        now_minutes = now.hour * 60 + now.minute
        cutover_minutes = hh * 60 + mm
        minutes_remaining = cutover_minutes - now_minutes
        if 0 <= minutes_remaining < min_minutes:
            return False, (
                f"Too close to flat-close cutover ({cutover_str} UTC) — "
                f"{minutes_remaining}min remaining, need {min_minutes}min"
            )
        return True, "OK"

    def _scan_pair(self, pair: str) -> None:
        """
        Scan a single pair and generate signal if conditions are met.
        Avoids duplicate scans on the same candle.
        """
        # Check if we already scanned this candle
        # Small fetch just to check whether a new candle has formed
        df_check = mt5_engine.get_candles(pair, "M15", count=5)
        if df_check is None or len(df_check) < 2:
            return

        last_candle_time = str(df_check.index[-1])
        if self._last_scan_candle.get(pair) == last_candle_time:
            return  # Already scanned this candle — waiting for next M15 close

        self._last_scan_candle[pair] = last_candle_time

        # Fetch full history for indicators (EMA200 needs 200+ bars)
        df_m15 = mt5_engine.get_candles(pair, "M15", count=300)
        if df_m15 is None or len(df_m15) < 210:
            logger.warning(f"{pair}: Loading history ({len(df_m15) if df_m15 is not None else 0}/210 bars) — waiting")
            return

        # Get M15 indicators to determine signal direction
        from strategies.indicators import calculate_indicators
        m15_ind = calculate_indicators(df_m15, pair)
        if not m15_ind:
            return

        # Build multi-timeframe data dict for signal engine
        df_h1 = mt5_engine.get_candles(pair, "H1",  count=100)
        df_h4 = mt5_engine.get_candles(pair, "H4",  count=100)
        df_d1 = mt5_engine.get_candles(pair, "D1",  count=250)
        data_by_tf = {
            "M15": df_m15,
            "H1":  df_h1,
            "H4":  df_h4,
            "D1":  df_d1,
        }

        # ── New signal engine — replaces old trend_direction logic ──
        signal = generate_signal(data_by_tf, pair)
        direction = signal.get("signal_direction", "NEUTRAL")

        if direction == "NEUTRAL":
            logger.debug(f"NEUTRAL {pair} | {signal.get('trigger', 'no trigger')}")
            return

        adx = m15_ind.get("adx", 0)
        rsi = m15_ind.get("rsi", 50)
        logger.info(
            f"Signal {pair} {direction} | Trigger={signal['trigger']} | "
            f"Bias={signal.get('htf_context', signal.get('higher_tf_bias','?'))} | "
            f"Structure={signal.get('ms_structure','?')} | "
            f"ADX={adx:.0f} | RSI={rsi:.0f} | "
            f"Entry={signal['entry_price']:.5f}"
        )

        self._evaluate_and_execute(pair, direction, signal=signal)


# ============================================================
# Main Entry Point
# ============================================================

def run_system():
    """
    Start the complete trading system:
    1. Connect to MT5
    2. Start trade monitor
    3. Start autonomous scanner
    4. Start webhook server
    """
    import uvicorn
    from tradingview_webhook.webhook_server import app

    logger.info("=== ForexAI Trader Starting ===")

    # Connect MT5
    if not mt5_engine.connect():
        logger.error("MT5 connection failed. Exiting.")
        return

    # Seed today's peak balance/drawdown baseline before the first trade
    try:
        account = mt5_engine.get_account_info()
        if account:
            stats = get_daily_stats()
            update_drawdown(account["equity"], stats.get("peak_balance", 0.0))
    except Exception as e:
        logger.warning(f"Could not seed drawdown baseline: {e}")

    # Start trade monitor
    trade_monitor.start()

    # Start autonomous scanner
    orchestrator = TradingOrchestrator()
    orchestrator.start_autonomous_scanner()

    # Start webhook server (blocking)
    logger.info(f"Starting webhook server on port {config.get('webhook', 'port')}")
    uvicorn.run(
        app,
        host=config.get("webhook", "host"),
        port=config.get("webhook", "port"),
        log_level="warning",
    )


if __name__ == "__main__":
    run_system()
