"""
mt5_execution/mt5_engine.py
---------------------------
MetaTrader 5 Python API integration.
Handles all trade execution, modification, and closing.

Features:
  - Connection management with auto-reconnect
  - Order execution with retry logic
  - Slippage/deviation handling
  - Partial close support
  - SL/TP modification
  - Trade monitoring loop
  - Error handling for all MT5 return codes

IMPORTANT: This module runs on Windows only (MT5 API limitation).
For Linux VPS, run MT5 in Wine or use a Windows cloud VPS.
"""

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from core.config_manager import config
from core.logger import get_logger, TradeLogger
from core.state_manager import (
    save_active_trade, remove_active_trade, get_active_trades,
    append_trade_history, update_daily_stats
)
from strategies.indicators import get_pip_value

logger = get_logger(__name__)

# Attempt MT5 import (only works on Windows with MT5 installed)
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 module not found. Running in SIMULATION mode.")


class MT5Engine:
    """
    Complete MT5 trade execution and management engine.
    Falls back to simulation mode if MT5 is unavailable.
    """

    def __init__(self):
        self.connected = False
        self.simulation_mode = not MT5_AVAILABLE
        self._connection_attempts = 0

    # ============================================================
    # Connection Management
    # ============================================================

    def connect(self) -> bool:
        """Initialize MT5 connection. Returns True on success."""
        if self.simulation_mode:
            logger.info("MT5 SIMULATION MODE active")
            self.connected = True
            return True

        mt5_cfg = config.full["mt5"]
        for attempt in range(config.get("mt5", "reconnect_attempts", default=5)):
            try:
                if not mt5.initialize(
                    path=mt5_cfg.get("path", ""),
                    login=mt5_cfg["login"],
                    password=mt5_cfg["password"],
                    server=mt5_cfg["server"],
                    timeout=10000
                ):
                    err = mt5.last_error()
                    logger.warning(f"MT5 init attempt {attempt+1} failed: {err}")
                    time.sleep(3)
                    continue

                info = mt5.account_info()
                if info:
                    logger.info(
                        f"MT5 connected | Account: {info.login} | "
                        f"Balance: {info.balance:.2f} {info.currency} | "
                        f"Server: {info.server}"
                    )
                    self.connected = True
                    self._connection_attempts = 0
                    return True
            except Exception as e:
                logger.error(f"MT5 connection exception: {e}")
                time.sleep(5)

        logger.error("MT5 connection failed after all attempts")
        return False

    def disconnect(self) -> None:
        if MT5_AVAILABLE and self.connected:
            mt5.shutdown()
        self.connected = False
        logger.info("MT5 disconnected")

    def ensure_connected(self) -> bool:
        """Reconnect if disconnected."""
        if self.simulation_mode:
            return True
        if not self.connected or not mt5.terminal_info():
            logger.warning("MT5 disconnected — attempting reconnect")
            return self.connect()
        return True

    def get_account_info(self) -> Optional[Dict]:
        """Return account balance, equity, margin info."""
        if self.simulation_mode:
            return {"balance": 10000.0, "equity": 10000.0, "margin_free": 9000.0, "currency": "USD"}
        if not self.ensure_connected():
            return None
        info = mt5.account_info()
        if info:
            return {
                "balance": info.balance,
                "equity": info.equity,
                "margin_free": info.margin_free,
                "currency": info.currency,
                "profit": info.profit,
                "margin": info.margin,
                "leverage": info.leverage,
            }
        return None

    def get_pip_value_usd_per_lot(self, pair: str) -> float:
        """
        USD value of 1 pip for a 1.0 standard lot, from live MT5 symbol data
        (trade_tick_value / trade_tick_size), correctly reflecting the
        broker's real contract specs. Falls back to the static
        SPREAD_USD_PER_PIP_01_LOT approximation in simulation mode or if the
        live lookup fails.
        """
        from risk_management.risk_engine import SPREAD_USD_PER_PIP_01_LOT
        fallback = SPREAD_USD_PER_PIP_01_LOT.get(pair, 1.0) * 10

        if self.simulation_mode or not self.ensure_connected():
            return fallback
        try:
            sym = mt5.symbol_info(pair)
            if not sym or not sym.trade_tick_size:
                return fallback
            pip = get_pip_value(pair)
            pip_value = sym.trade_tick_value / sym.trade_tick_size * pip
            return pip_value if pip_value > 0 else fallback
        except Exception as e:
            logger.debug(f"get_pip_value_usd_per_lot fallback for {pair}: {e}")
            return fallback

    def get_margin_usd_per_lot(self, pair: str) -> Optional[float]:
        """
        Approximate USD margin required per 1.0 standard lot, from live
        contract size / current price / account leverage. Returns None in
        simulation mode or on lookup failure — callers should treat that as
        "margin check unavailable, skip it" rather than "zero margin needed".
        """
        if self.simulation_mode or not self.ensure_connected():
            return None
        try:
            sym = mt5.symbol_info(pair)
            tick = mt5.symbol_info_tick(pair)
            account = mt5.account_info()
            if not sym or not tick or not account or not account.leverage:
                return None
            contract_size = sym.trade_contract_size or 100000
            return (contract_size * tick.ask) / account.leverage
        except Exception as e:
            logger.debug(f"get_margin_usd_per_lot fallback for {pair}: {e}")
            return None

    # ============================================================
    # Symbol Info
    # ============================================================

    def get_symbol_info(self, pair: str) -> Optional[Dict]:
        """Get current price and symbol info."""
        if self.simulation_mode:
            return {
                "bid": 1.10000, "ask": 1.10015, "spread": 1.5,
                "point": get_pip_value(pair), "trade_stops_level": 3
            }
        if not self.ensure_connected():
            return None
        try:
            mt5.symbol_select(pair, True)
            tick = mt5.symbol_info_tick(pair)
            sym  = mt5.symbol_info(pair)
            if tick and sym:
                pip = get_pip_value(pair)
                spread_pips = (tick.ask - tick.bid) / pip
                return {
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "spread": round(spread_pips, 1),
                    "point": sym.point,
                    "trade_stops_level": sym.trade_stops_level,
                    "volume_min": sym.volume_min,
                    "volume_max": sym.volume_max,
                    "volume_step": sym.volume_step,
                }
        except Exception as e:
            logger.error(f"get_symbol_info failed for {pair}: {e}")
        return None

    # ============================================================
    # Order Execution
    # ============================================================

    def open_trade(
        self,
        pair: str,
        direction: str,
        lot_size: float,
        sl: float,
        tp: float,
        comment: str = "ForexAI",
        confidence: float = 0.0,
    ) -> Optional[Dict]:
        """
        Open a market order.
        Returns trade dict on success, None on failure.
        """
        if not self.ensure_connected():
            logger.error("Cannot open trade: MT5 not connected")
            return None

        sym_info = self.get_symbol_info(pair)
        if not sym_info:
            return None

        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        price = sym_info["ask"] if direction == "BUY" else sym_info["bid"]

        if self.simulation_mode:
            ticket = int(time.time() * 1000) % 1000000
            trade = {
                "ticket": ticket,
                "pair": pair,
                "direction": direction,
                "lot_size": lot_size,
                "open_price": price,
                "sl": sl,
                "tp": tp,
                "open_time": datetime.now(timezone.utc).isoformat(),
                "confidence": confidence,
                "partial_closed": False,
                "be_moved": False,
                "trailing_active": False,
                "comment": comment,
            }
            save_active_trade(ticket, trade)
            TradeLogger.log("TRADE_OPEN", trade)
            logger.info(f"[SIM] Trade opened: {pair} {direction} @ {price} | SL={sl} TP={tp} | Lot={lot_size}")
            return trade

        # Real MT5 execution
        # Try all filling modes — different brokers support different ones
        # OctaFX / most ECN brokers use FOK; some use IOC or RETURN
        for filling_mode in (mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN):
            request = {
                "action":   mt5.TRADE_ACTION_DEAL,
                "symbol":   pair,
                "volume":   lot_size,
                "type":     order_type,
                "price":    price,
                "sl":       sl,
                "tp":       tp,
                "deviation": config.get("mt5", "deviation"),
                "magic":    config.magic_number,
                "comment":  comment[:31],  # MT5 comment limit
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }
            result = self._execute_with_retry(request, pair, direction, lot_size, sl, tp, confidence)
            if result is not None:
                return result
            logger.debug(f"{pair}: Filling mode {filling_mode} failed, trying next...")
        return None

    def _execute_with_retry(
        self, request: Dict, pair: str, direction: str,
        lot_size: float, sl: float, tp: float, confidence: float
    ) -> Optional[Dict]:
        """Execute order with retry logic and requote handling."""
        attempts = config.get("mt5", "retry_attempts", default=3)
        delay = config.get("mt5", "retry_delay_seconds", default=1)

        for attempt in range(attempts):
            result = mt5.order_send(request)

            if result is None:
                logger.error(f"order_send returned None for {pair}")
                time.sleep(delay)
                continue

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                # Success
                open_price = result.price
                trade = {
                    "ticket": result.order,
                    "pair": pair,
                    "direction": direction,
                    "lot_size": lot_size,
                    "open_price": open_price,
                    "sl": sl,
                    "tp": tp,
                    "open_time": datetime.now(timezone.utc).isoformat(),
                    "confidence": confidence,
                    "partial_closed": False,
                    "be_moved": False,
                    "trailing_active": False,
                }
                save_active_trade(result.order, trade)
                TradeLogger.log("TRADE_OPEN", trade)
                logger.info(
                    f"Trade OPENED: {pair} {direction} #{result.order} "
                    f"@ {open_price} | SL={sl} | TP={tp} | Lot={lot_size}"
                )
                return trade

            elif result.retcode in (
                mt5.TRADE_RETCODE_REQUOTE, mt5.TRADE_RETCODE_PRICE_CHANGED
            ):
                # Requote: update price and retry
                tick = mt5.symbol_info_tick(pair)
                if tick:
                    request["price"] = tick.ask if direction == "BUY" else tick.bid
                logger.warning(f"Requote on {pair} — retry {attempt+1}")
                time.sleep(delay)

            else:
                logger.error(
                    f"Order failed: {pair} | Code={result.retcode} | "
                    f"Comment={result.comment}"
                )
                # Code 10030 = unsupported filling mode — return immediately
                # so caller can retry with a different filling mode
                if result.retcode == 10030:
                    return None
                if attempt < attempts - 1:
                    time.sleep(delay)

        logger.error(f"Order failed after {attempts} attempts: {pair}")
        return None

    # ============================================================
    # Trade Modification
    # ============================================================

    def modify_sl_tp(
        self,
        ticket: int,
        new_sl: float,
        new_tp: Optional[float] = None,
    ) -> bool:
        """Modify SL/TP of existing position."""
        if self.simulation_mode:
            from core.state_manager import get_active_trade
            trade = get_active_trade(ticket)
            if trade:
                trade["sl"] = new_sl
                if new_tp:
                    trade["tp"] = new_tp
                save_active_trade(ticket, trade)
            logger.info(f"[SIM] Modified #{ticket} SL={new_sl}" + (f" TP={new_tp}" if new_tp else ""))
            return True

        if not self.ensure_connected():
            return False

        from core.state_manager import get_active_trade
        trade = get_active_trade(ticket)
        if not trade:
            return False

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": trade["pair"],
            "sl": new_sl,
            "tp": new_tp or trade.get("tp", 0),
            "position": ticket,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            trade["sl"] = new_sl
            if new_tp:
                trade["tp"] = new_tp
            save_active_trade(ticket, trade)
            logger.info(f"Modified #{ticket} SL={new_sl}")
            return True
        else:
            logger.error(f"Modify failed #{ticket}: {result.retcode if result else 'None'}")
            return False

    def close_trade(
        self,
        ticket: int,
        reason: str = "manual",
        volume: Optional[float] = None,
    ) -> Optional[Dict]:
        """
        Close position fully or partially.
        Returns closed trade dict with profit info.
        """
        from core.state_manager import get_active_trade
        trade = get_active_trade(ticket)
        if not trade:
            logger.warning(f"close_trade: ticket #{ticket} not found in active trades")
            return None

        pair      = trade["pair"]
        direction = trade["direction"]
        lot_size  = volume or trade["lot_size"]

        sym_info = self.get_symbol_info(pair)
        if not sym_info:
            return None

        close_price = sym_info["bid"] if direction == "BUY" else sym_info["ask"]

        if self.simulation_mode:
            pip = get_pip_value(pair)
            pips = (close_price - trade["open_price"]) / pip
            if direction == "SELL":
                pips = -pips
            profit = pips * lot_size * 10  # Simplified P&L
            won = profit > 0

            closed = {**trade, "close_price": close_price, "close_time": datetime.now(timezone.utc).isoformat(),
                      "profit_usd": round(profit, 2), "pips": round(pips, 1), "exit_reason": reason}

            is_partial = volume and volume < trade["lot_size"]
            if not is_partial:
                remove_active_trade(ticket)
                append_trade_history(closed)
                update_daily_stats(profit, pair, won)
                TradeLogger.log("TRADE_CLOSE", closed)
                logger.info(f"[SIM] Closed #{ticket} {pair} {direction} | Profit=${profit:.2f} | Reason={reason}")
            else:
                trade["lot_size"] -= volume
                trade["partial_closed"] = True
                save_active_trade(ticket, trade)
                logger.info(f"[SIM] Partial close #{ticket} {volume} lots | Profit=${profit:.2f}")
            return closed

        # Real MT5 close
        order_type = mt5.ORDER_TYPE_SELL if direction == "BUY" else mt5.ORDER_TYPE_BUY
        result = None
        for filling_mode in (mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN):
            request = {
                "action":   mt5.TRADE_ACTION_DEAL,
                "symbol":   pair,
                "volume":   lot_size,
                "type":     order_type,
                "position": ticket,
                "price":    close_price,
                "deviation": config.get("mt5", "deviation"),
                "magic":    config.magic_number,
                "comment":  reason[:31],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                break
            if result and result.retcode == 10030:
                continue  # unsupported filling mode — try next
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            pip = get_pip_value(pair)
            close_px = result.price

            # OrderSendResult has no .profit — calculate from price move
            open_px = trade.get("open_price", close_px)
            raw_pips = (close_px - open_px) / pip
            if direction == "SELL":
                raw_pips = -raw_pips
            pips = raw_pips

            # Estimate profit: pips × pip_value_per_lot × lots
            # For non-JPY: pip value ≈ $1 per 0.01 lot per pip
            # For JPY: pip value ≈ $0.91 per 0.01 lot per pip (approx)
            pip_value_per_lot = 100 if "JPY" not in pair.upper() else 91
            profit = round(raw_pips * pip_value_per_lot * lot_size / 100, 2)

            # Try to get actual profit from MT5 deal history (more accurate)
            try:
                import MetaTrader5 as _mt5
                from datetime import timedelta
                deals = _mt5.history_deals_get(
                    datetime.now(timezone.utc) - timedelta(minutes=2),
                    datetime.now(timezone.utc) + timedelta(minutes=1)
                )
                if deals:
                    matching = [d for d in deals if d.position_id == ticket]
                    if matching:
                        profit = sum(d.profit for d in matching)
            except Exception:
                pass  # Use estimated profit

            closed = {
                **trade,
                "close_price": result.price,
                "close_time": datetime.now(timezone.utc).isoformat(),
                "profit_usd": round(profit, 2),
                "pips": round(pips, 1),
                "exit_reason": reason,
            }
            remove_active_trade(ticket)
            append_trade_history(closed)
            update_daily_stats(profit, pair, profit > 0)
            TradeLogger.log("TRADE_CLOSE", closed)
            logger.info(f"Closed #{ticket} {pair} | Profit=${profit:.2f} | Reason={reason}")
            return closed
        else:
            logger.error(f"Close failed #{ticket}: {result.retcode if result else 'None'}")
            return None

    # ============================================================
    # Position Monitoring
    # ============================================================

    def get_open_positions(self) -> List[Dict]:
        """Get all open MT5 positions filtered by magic number."""
        if self.simulation_mode:
            return list(get_active_trades().values())

        if not self.ensure_connected():
            return []

        positions = mt5.positions_get(group="*") or []
        result = []
        for pos in positions:
            if pos.magic == config.magic_number:
                result.append({
                    "ticket": pos.ticket,
                    "pair": pos.symbol,
                    "direction": "BUY" if pos.type == 0 else "SELL",
                    "lot_size": pos.volume,
                    "open_price": pos.price_open,
                    "current_price": pos.price_current,
                    "sl": pos.sl,
                    "tp": pos.tp,
                    "profit": pos.profit,
                    "open_time": datetime.fromtimestamp(pos.time, tz=timezone.utc).isoformat(),
                })
        return result

    def get_candles(
        self,
        pair: str,
        timeframe: str,
        count: int = 300
    ):
        """
        Fetch OHLCV candles from MT5.
        Returns pandas DataFrame or None.
        """
        import pandas as pd

        TF_MAP = {
            "M15": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15,
            "H1":  mt5.TIMEFRAME_H1  if MT5_AVAILABLE else 60,
            "H4":  mt5.TIMEFRAME_H4  if MT5_AVAILABLE else 240,
            "D1":  mt5.TIMEFRAME_D1  if MT5_AVAILABLE else 1440,
        }

        if self.simulation_mode:
            # Return synthetic data for testing
            return self._generate_synthetic_candles(pair, count)

        if not self.ensure_connected():
            return None

        tf = TF_MAP.get(timeframe)
        if tf is None:
            logger.error(f"Unknown timeframe: {timeframe}")
            return None

        mt5.symbol_select(pair, True)
        rates = mt5.copy_rates_from_pos(pair, tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.warning(f"No candle data for {pair} {timeframe}")
            return None

        df = pd.DataFrame(rates)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)
        return df[["open", "high", "low", "close", "volume"]]

    def _generate_synthetic_candles(self, pair: str, count: int):
        """Generate synthetic OHLCV for simulation/testing."""
        import pandas as pd
        import numpy as np

        np.random.seed(42)
        base = 1.1000
        returns = np.random.normal(0, 0.0005, count)
        closes = base + np.cumsum(returns)
        highs  = closes + np.abs(np.random.normal(0, 0.0002, count))
        lows   = closes - np.abs(np.random.normal(0, 0.0002, count))
        opens  = np.roll(closes, 1)
        opens[0] = base

        df = pd.DataFrame({
            "open": opens, "high": highs, "low": lows,
            "close": closes, "volume": np.random.randint(100, 1000, count)
        })
        return df


# Module-level singleton
mt5_engine = MT5Engine()
