"""
mt5_execution/trade_monitor.py
------------------------------
Continuous trade management loop.
Runs independently in a background thread.

Responsibilities (checked every 30 seconds):
  1. Break-even movement
  2. Trailing stop loss
  3. Partial profit booking
  4. Time-based exit
  5. Volatility-based exit
  6. News-based emergency exit
  7. Sync active_trades.json with MT5 reality

This is the "active trade manager" — it protects profits
and adapts dynamically to changing market conditions.
"""

import time
import threading
from datetime import datetime, timezone
from typing import Dict, Optional

from core.config_manager import config
from core.logger import get_logger
from core.state_manager import get_active_trades, is_kill_switch_active, get_daily_stats, update_drawdown
from mt5_execution.mt5_engine import mt5_engine
from risk_management.risk_engine import risk_engine
from strategies.indicators import get_pip_value

logger = get_logger(__name__)


class TradeMonitor:
    """
    Background trade management daemon.
    Spawns as a separate thread. Thread-safe via state_manager locking.
    """

    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="TradeMonitor",
            daemon=True
        )
        self._thread.start()
        logger.info("Trade monitor started")

    def stop(self) -> None:
        """Stop the monitoring thread gracefully."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Trade monitor stopped")

    def _monitor_loop(self) -> None:
        """Main monitoring loop. Runs every check_interval seconds."""
        _cycle = 0
        while self._running:
            try:
                self._update_drawdown()
                if is_kill_switch_active():
                    logger.warning("Kill switch active — closing all positions")
                    self._close_all("kill_switch")
                elif self._past_flat_close_cutover() and get_active_trades():
                    logger.info(
                        "Flat-close cutover reached — closing all open positions "
                        "(strict same-day intraday rule)"
                    )
                    self._close_all("flat_close_cutover")
                else:
                    self._check_all_trades()
                _cycle += 1
                if _cycle % 5 == 0:
                    self._log_positions()
            except Exception as e:
                logger.error(f"Trade monitor error: {e}", exc_info=True)

            time.sleep(self.check_interval)

    def _update_drawdown(self) -> None:
        """Refresh current_drawdown_pct from live equity every cycle.

        Uses equity (not balance) so the daily/weekly drawdown circuit
        breakers in risk_engine.can_take_trade() react to floating losses
        on open positions, not just realized P&L.
        """
        try:
            account = mt5_engine.get_account_info()
            if not account:
                return
            stats = get_daily_stats()
            update_drawdown(account["equity"], stats.get("peak_balance", 0.0))
        except Exception as e:
            logger.debug(f"Drawdown update error: {e}")

    def _past_flat_close_cutover(self) -> bool:
        """True once wall-clock UTC time has reached the daily flat-close cutover."""
        cutover_str = config.get("risk", "flat_close_cutover_utc", default="21:00")
        try:
            hh, mm = (int(x) for x in cutover_str.split(":"))
        except Exception:
            hh, mm = 21, 0
        now = datetime.now(timezone.utc)
        return (now.hour * 60 + now.minute) >= (hh * 60 + mm)

    def _log_positions(self) -> None:
        """Log summary of all open positions every ~2.5 minutes."""
        try:
            import MetaTrader5 as mt5
            positions = mt5.positions_get()
            if not positions:
                logger.info("[Monitor] No open positions")
                return
            for p in positions:
                pip  = 0.01 if "JPY" in p.symbol else 0.0001
                tick = mt5.symbol_info_tick(p.symbol)
                cur  = (tick.bid if p.type == 1 else tick.ask) if tick else p.price_open
                pips = ((cur - p.price_open) / pip) if p.type == 0 else ((p.price_open - cur) / pip)
                sl_p = abs(p.price_open - p.sl) / pip if p.sl else 0
                tp_p = abs(p.tp - p.price_open) / pip if p.tp else 0
                logger.info(
                    f"[Monitor] #{p.ticket} {p.symbol} {'BUY' if p.type==0 else 'SELL'} "
                    f"{p.volume}lot @ {p.price_open:.5f} | "
                    f"Now={cur:.5f} | Pips={pips:+.1f} | "
                    f"P&L=${p.profit:+.2f} | "
                    f"SL={p.sl:.5f}(-{sl_p:.0f}p) TP={p.tp:.5f}(+{tp_p:.0f}p)"
                )
        except Exception as e:
            logger.debug(f"Position log error: {e}")

    def _check_all_trades(self) -> None:
        """Check all active trades and apply management rules."""
        active_trades = get_active_trades()
        if not active_trades:
            return

        # Get current MT5 positions for truth check
        mt5_positions = {str(p["ticket"]): p for p in mt5_engine.get_open_positions()}

        for ticket_str, trade in list(active_trades.items()):
            ticket = int(ticket_str)
            pair = trade.get("pair")
            direction = trade.get("direction")

            # Sync: if position closed by MT5 (SL/TP hit), update state
            if ticket_str not in mt5_positions and not mt5_engine.simulation_mode:
                logger.info(f"Position #{ticket} no longer in MT5 — SL/TP hit, syncing")
                from core.state_manager import remove_active_trade, append_trade_history, update_daily_stats
                from datetime import timedelta
                closed = remove_active_trade(ticket)
                if closed:
                    # Look up actual close data from MT5 deal history
                    try:
                        import MetaTrader5 as _mt5
                        from datetime import datetime as _dt, timezone as _tz
                        open_dt = _dt.fromisoformat(closed.get("open_time", ""))
                        if open_dt.tzinfo is None:
                            open_dt = open_dt.replace(tzinfo=_tz.utc)
                        deals = _mt5.history_deals_get(
                            open_dt - timedelta(minutes=5),
                            _dt.now(_tz.utc) + timedelta(minutes=1)
                        )
                        if deals:
                            # Find closing deal for this position (entry=1 means close)
                            close_deals = [d for d in deals
                                           if d.position_id == ticket and d.entry == 1]
                            if close_deals:
                                d = close_deals[-1]
                                pip = 0.01 if "JPY" in pair.upper() else 0.0001
                                open_px = closed.get("open_price", d.price)
                                raw_pips = (d.price - open_px) / pip
                                if closed.get("direction") == "SELL":
                                    raw_pips = -raw_pips
                                profit = sum(x.profit for x in close_deals)
                                closed.update({
                                    "close_price": round(d.price, 5),
                                    "close_time":  _dt.fromtimestamp(d.time, tz=_tz.utc).isoformat(),
                                    "pips":        round(raw_pips, 1),
                                    "profit_usd":  round(profit, 2),
                                })
                                update_daily_stats(profit, pair, profit > 0)
                                logger.info(
                                    f"SL/TP sync #{ticket} {pair} | "
                                    f"Close={d.price:.5f} | Pips={raw_pips:.1f} | "
                                    f"P&L=${profit:.2f}"
                                )
                    except Exception as e:
                        logger.warning(f"Could not fetch deal history for #{ticket}: {e}")
                    closed["exit_reason"] = "sl_tp_hit"
                    append_trade_history(closed)
                continue

            # Get current price
            sym = mt5_engine.get_symbol_info(pair)
            if not sym:
                continue

            current_price = sym["bid"] if direction == "BUY" else sym["ask"]
            # Use live MT5 position data for SL/TP (may have been modified)
            mt5_pos = mt5_positions.get(ticket_str, {})
            current_sl = mt5_pos.get("sl") or trade.get("sl", 0)
            tp         = mt5_pos.get("tp") or trade.get("tp", 0)
            open_price = mt5_pos.get("open_price") or trade.get("open_price", current_price)

            # ---- Fetch current ATR for dynamic trailing ----
            atr_pips = self._get_current_atr(pair)

            # ---- 1. Break-even movement ----
            if not trade.get("be_moved", False):
                should_move, new_sl = risk_engine.should_move_to_breakeven(
                    direction, open_price, current_price, tp, current_sl
                )
                if should_move and new_sl:
                    if mt5_engine.modify_sl_tp(ticket, new_sl):
                        trade["be_moved"] = True
                        from core.state_manager import save_active_trade
                        save_active_trade(ticket, trade)
                        logger.info(f"Break-even set for #{ticket} {pair} @ {new_sl}")

            # ---- 2. Trailing stop ----
            if trade.get("be_moved", False):  # Only trail after BE
                new_trail_sl = risk_engine.calculate_trailing_sl(
                    pair, direction, current_price, current_sl, atr_pips,
                    open_price=open_price,
                )
                if new_trail_sl:
                    if mt5_engine.modify_sl_tp(ticket, new_trail_sl):
                        trade["trailing_active"] = True
                        from core.state_manager import save_active_trade
                        save_active_trade(ticket, trade)
                        logger.debug(f"Trailing SL moved #{ticket}: {new_trail_sl}")

            # ---- 3. Staged partial closes — DISABLED ----
            # Partial closes hurt performance: they reduce lot size before TP
            # then the remaining position hits SL for full loss on smaller size
            # Net effect: small partial profit wiped by full SL on remainder
            # Trade history confirmed: 15 partials collected $6.56 but 
            # remaining positions then lost $20.71 on SL hits
            # partial_close_at_rr is set to 9.9 in config to disable
            _partial_disabled = (config.get("risk", "partial_close_at_rr") or 1.0) >= 9.0
            if not _partial_disabled:
                partial_done   = trade.get("partial_closed",   False)
                partial_2_done = trade.get("partial_2_closed", False)
                should_close, stage = risk_engine.should_partial_close(
                    direction, open_price, current_price, tp,
                    partial_done, partial_2_done, current_sl
                )
                if should_close:
                    if stage == 1:
                        pct = config.get("risk", "partial_close_pct") or 33
                        reason = "partial_profit_1"
                    else:
                        pct = config.get("risk", "partial_close_2_pct") or 33
                        reason = "partial_profit_2"
                    partial_lot = round(trade["lot_size"] * (pct / 100), 2)
                    if partial_lot >= 0.01:
                        result = mt5_engine.close_trade(ticket, reason=reason, volume=partial_lot)
                        if result:
                            from core.state_manager import save_active_trade
                            if stage == 1:
                                trade["partial_closed"] = True
                            else:
                                trade["partial_2_closed"] = True
                            save_active_trade(ticket, trade)
                            logger.info(f"Stage-{stage} partial close #{ticket} {pair} — {partial_lot} lots ({pct}%)")

            # ---- 4. Time-based exit: superseded by the daily flat-close cutover ----
            # (see _monitor_loop / _past_flat_close_cutover) — strict same-day
            # intraday rule now force-closes ALL positions at a fixed UTC time
            # regardless of P&L, replacing the old "up to 24h, exit only if
            # at breakeven/loss" behavior.

    def _get_current_atr(self, pair: str) -> float:
        """Get current ATR in pips for trailing calculations.
        Uses raw candle data directly — avoids the 210-bar minimum
        required by calculate_indicators (trade monitor only needs ATR).
        """
        try:
            from strategies.indicators import get_pip_value as _pip
            df = mt5_engine.get_candles(pair, "M15", count=30)
            if df is not None and len(df) >= 15:
                tr = (df["high"] - df["low"]).rolling(14).mean()
                atr_raw = tr.iloc[-1]
                if atr_raw and atr_raw > 0:
                    return round(atr_raw / _pip(pair), 1)
        except Exception:
            pass
        return 15.0  # Sensible default ATR in pips

    def _close_all(self, reason: str) -> None:
        """Close all open positions immediately (kill switch or flat-close cutover)."""
        active_trades = get_active_trades()
        for ticket_str in list(active_trades.keys()):
            try:
                mt5_engine.close_trade(int(ticket_str), reason=reason)
                logger.warning(f"Closed #{ticket_str} ({reason})")
            except Exception as e:
                logger.error(f"Close failed #{ticket_str} ({reason}): {e}")


# Module-level singleton
trade_monitor = TradeMonitor()
