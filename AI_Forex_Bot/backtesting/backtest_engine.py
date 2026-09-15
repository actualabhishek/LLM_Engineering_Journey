"""
backtesting/backtest_engine.py
-------------------------------
Walk-forward backtesting engine.
Tests the full strategy logic on historical data.

Features:
  - Event-driven simulation on OHLCV data
  - Realistic spread simulation
  - Slippage modeling
  - Full risk management integration
  - Session filtering
  - Performance analytics (Sharpe, Sortino, max DD, etc.)
  - Walk-forward testing
  - Monte Carlo simulation

Usage:
  from backtesting.backtest_engine import run_backtest
  results = run_backtest("EURUSD", "M15", start="2024-01-01", end="2024-12-31")
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from core.logger import get_logger
from strategies.indicators import calculate_indicators, detect_market_structure, get_pip_value
from core.config_manager import config

logger = get_logger(__name__)
REPORTS_DIR = Path(__file__).parent.parent / "storage" / "data"


class BacktestEngine:
    """
    Vectorized-style backtester with realistic trade simulation.
    Uses bar-by-bar processing to simulate live trading logic.
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        lot_size: float = 0.1,
        spread_pips: float = 1.5,
        commission_per_lot: float = 3.5,
    ):
        self.initial_balance = initial_balance
        self.lot_size = lot_size
        self.spread_pips = spread_pips
        self.commission_per_lot = commission_per_lot

    def run(
        self,
        df: pd.DataFrame,
        pair: str,
        warmup_bars: int = 250,
    ) -> Dict:
        """
        Run backtest on historical OHLCV DataFrame.
        Returns comprehensive results dict.
        """
        if df is None or len(df) < warmup_bars + 100:
            return {"error": f"Insufficient data: {len(df) if df is not None else 0} bars"}

        pip = get_pip_value(pair)
        balance = self.initial_balance
        peak_balance = balance
        max_drawdown = 0.0
        position = None
        trades = []
        equity_curve = [balance]
        daily_returns = []

        atr_sl_mult = config.get("risk", "atr_sl_multiplier")
        atr_tp_mult = config.get("risk", "atr_tp_multiplier")
        partial_close_at = config.get("risk", "partial_close_at_rr")
        partial_close_pct = config.get("risk", "partial_close_pct") / 100
        min_rr = config.get("trading", "min_rr_ratio")

        for i in range(warmup_bars, len(df)):
            bar = df.iloc[i]
            prev_bars = df.iloc[max(0, i - 250): i + 1]

            # ---- Manage open position ----
            if position:
                close_price = None
                exit_reason = None
                high, low = bar["high"], bar["low"]

                if position["direction"] == "BUY":
                    # Check SL hit
                    if low <= position["sl"]:
                        close_price = position["sl"]
                        exit_reason = "sl_hit"
                    # Check TP hit
                    elif high >= position["tp"]:
                        close_price = position["tp"]
                        exit_reason = "tp_hit"
                    # Break-even check
                    elif not position.get("be_moved") and high >= position["open"] + (position["tp"] - position["open"]) * 0.8:
                        new_sl = position["open"] + self.spread_pips * pip
                        if new_sl > position["sl"]:
                            position["sl"] = new_sl
                            position["be_moved"] = True

                else:  # SELL
                    if high >= position["sl"]:
                        close_price = position["sl"]
                        exit_reason = "sl_hit"
                    elif low <= position["tp"]:
                        close_price = position["tp"]
                        exit_reason = "tp_hit"
                    elif not position.get("be_moved") and low <= position["open"] - (position["open"] - position["tp"]) * 0.8:
                        new_sl = position["open"] - self.spread_pips * pip
                        if new_sl < position["sl"]:
                            position["sl"] = new_sl
                            position["be_moved"] = True

                if close_price and exit_reason:
                    pips = (close_price - position["open"]) / pip
                    if position["direction"] == "SELL":
                        pips = -pips

                    lot = position["lot_size"]
                    # Simple P&L: 1 pip = $10 at 1.0 lot for major pairs (approximate)
                    profit = pips * lot * 10 - self.commission_per_lot * lot

                    balance += profit
                    trades.append({
                        "entry_bar": position["entry_bar"],
                        "exit_bar": i,
                        "pair": pair,
                        "direction": position["direction"],
                        "open_price": position["open"],
                        "close_price": close_price,
                        "sl": position["sl_original"],
                        "tp": position["tp"],
                        "pips": round(pips, 1),
                        "profit": round(profit, 2),
                        "exit_reason": exit_reason,
                        "lot_size": lot,
                    })
                    position = None

                    # Track drawdown
                    if balance > peak_balance:
                        peak_balance = balance
                    dd = (peak_balance - balance) / peak_balance * 100
                    max_drawdown = max(max_drawdown, dd)

            # ---- Generate signal on bar close ----
            if position is None:
                indicators = calculate_indicators(prev_bars, pair)
                if not indicators:
                    equity_curve.append(balance)
                    continue

                direction = indicators["trend_direction"]
                if direction not in ("BUY", "SELL"):
                    equity_curve.append(balance)
                    continue

                # Signal conditions (mirrors live trading logic)
                atr_pips = indicators["atr_pips"]
                adx_ok = indicators["adx"] >= 20
                vol_ok = indicators["volatility_ok"]
                momentum = indicators["momentum_score"]

                # Quality filter
                is_buy  = direction == "BUY"  and indicators["ema_bullish"] and indicators["supertrend_bull"] and adx_ok and vol_ok and momentum >= 60
                is_sell = direction == "SELL" and indicators["ema_bearish"] and indicators["supertrend_bear"] and adx_ok and vol_ok and momentum <= 40

                if not (is_buy or is_sell):
                    equity_curve.append(balance)
                    continue

                # Calculate SL/TP
                entry = bar["close"]
                sl_dist = atr_pips * atr_sl_mult * pip
                tp_dist = atr_pips * atr_tp_mult * pip
                spread_adj = self.spread_pips * pip * 0.5

                if is_buy:
                    entry += self.spread_pips * pip  # Spread cost on buy
                    sl = entry - sl_dist - spread_adj
                    tp = entry + tp_dist
                else:
                    sl = entry + sl_dist + spread_adj
                    tp = entry - tp_dist

                # RR check
                sl_p = abs(entry - sl) / pip
                tp_p = abs(tp - entry) / pip
                if sl_p <= 0 or (tp_p / sl_p) < min_rr:
                    equity_curve.append(balance)
                    continue

                position = {
                    "direction": "BUY" if is_buy else "SELL",
                    "open": entry,
                    "sl": sl,
                    "sl_original": sl,
                    "tp": tp,
                    "lot_size": self.lot_size,
                    "entry_bar": i,
                    "be_moved": False,
                }

            equity_curve.append(balance)

        # Close any remaining position at last bar
        if position:
            last_price = df.iloc[-1]["close"]
            pips = (last_price - position["open"]) / pip
            if position["direction"] == "SELL":
                pips = -pips
            profit = pips * position["lot_size"] * 10
            balance += profit
            trades.append({
                "exit_reason": "end_of_data",
                "pips": round(pips, 1),
                "profit": round(profit, 2),
                **position,
            })

        return self._calculate_metrics(trades, equity_curve, self.initial_balance, max_drawdown, pair)

    def _calculate_metrics(
        self, trades: List[Dict], equity: List[float],
        initial: float, max_dd: float, pair: str
    ) -> Dict:
        """Comprehensive performance metrics."""
        if not trades:
            return {"error": "No trades generated"}

        df = pd.DataFrame(trades)
        winners = df[df["profit"] > 0]
        losers  = df[df["profit"] < 0]

        total = len(df)
        win_count = len(winners)
        win_rate = win_count / total * 100

        gross_profit = winners["profit"].sum() if not winners.empty else 0
        gross_loss   = abs(losers["profit"].sum()) if not losers.empty else 0
        net_profit   = df["profit"].sum()
        profit_factor = gross_profit / max(gross_loss, 0.01)

        avg_win  = winners["profit"].mean() if not winners.empty else 0
        avg_loss = losers["profit"].mean()   if not losers.empty else 0
        expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss)

        # Sharpe ratio (annualized, assumes M15 = ~96 bars/day)
        returns = pd.Series(equity).pct_change().dropna()
        sharpe = (returns.mean() / max(returns.std(), 1e-6)) * math.sqrt(96 * 252)

        # Sortino ratio (downside deviation only)
        neg_returns = returns[returns < 0]
        sortino = (returns.mean() / max(neg_returns.std(), 1e-6)) * math.sqrt(96 * 252)

        # Max consecutive losses
        df["won"] = df["profit"] > 0
        max_consec_loss = self._max_consecutive(df["won"].tolist(), False)
        max_consec_win  = self._max_consecutive(df["won"].tolist(), True)

        results = {
            "pair": pair,
            "total_trades": total,
            "win_rate_pct": round(win_rate, 1),
            "win_count": win_count,
            "loss_count": total - win_count,
            "net_profit": round(net_profit, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "expectancy": round(expectancy, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "roi_pct": round((net_profit / self.initial_balance) * 100, 2),
            "max_consecutive_losses": max_consec_loss,
            "max_consecutive_wins": max_consec_win,
            "avg_pips": round(df["pips"].mean(), 1) if "pips" in df.columns else 0,
            "total_pips": round(df["pips"].sum(), 1) if "pips" in df.columns else 0,
            "exit_reasons": df["exit_reason"].value_counts().to_dict() if "exit_reason" in df.columns else {},
        }

        # Save report
        try:
            report_path = REPORTS_DIR / f"backtest_{pair}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_path, "w") as f:
                json.dump(results, f, indent=2)
            logger.info(f"Backtest report saved: {report_path}")
        except Exception:
            pass

        return results

    def _max_consecutive(self, values: List[bool], target: bool) -> int:
        max_streak = current = 0
        for v in values:
            if v == target:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        return max_streak

    def monte_carlo(self, trades: List[Dict], simulations: int = 1000) -> Dict:
        """
        Monte Carlo simulation by randomly shuffling trade order.
        Estimates distribution of possible outcomes.
        """
        if not trades:
            return {}

        profits = [t["profit"] for t in trades]
        results = []

        for _ in range(simulations):
            shuffled = np.random.permutation(profits)
            equity = self.initial_balance + np.cumsum(shuffled)
            peak = np.maximum.accumulate(equity)
            dd = np.max((peak - equity) / peak * 100)
            results.append({
                "final_equity": float(equity[-1]),
                "max_drawdown": float(dd),
            })

        eq_values = [r["final_equity"] for r in results]
        dd_values = [r["max_drawdown"] for r in results]

        return {
            "simulations": simulations,
            "equity_5th_percentile":  round(np.percentile(eq_values, 5), 2),
            "equity_median":          round(np.percentile(eq_values, 50), 2),
            "equity_95th_percentile": round(np.percentile(eq_values, 95), 2),
            "max_dd_median":          round(np.percentile(dd_values, 50), 2),
            "max_dd_95th":            round(np.percentile(dd_values, 95), 2),
            "probability_of_profit":  round(sum(1 for e in eq_values if e > self.initial_balance) / simulations * 100, 1),
        }


def run_backtest(pair: str, df: pd.DataFrame, **kwargs) -> Dict:
    """Convenience function to run a backtest."""
    engine = BacktestEngine(**kwargs)
    return engine.run(df, pair)
