"""
backtesting/replay_backtest.py
-------------------------------
REAL strategy backtester — feeds historical bars through the
actual signal_engine, confidence_engine, and risk_engine.

This is NOT a simplified approximation. It runs:
  [x] detect_market_structure() — real swing detection
  [x] detect_momentum()         — real momentum expansion
  [x] trigger_liquidity_sweep() — real institutional detection
  [x] trigger_choch_entry()     — real CHOCH detection
  [x] is_overextended()         — real top/bottom prevention
  [x] is_choppy_market()        — real choppy detection
  [x] get_htf_context()         — real H1/H4/D1 bias
  [x] risk_engine.calculate_sl_tp()        — real confidence/session-tiered SL/TP
  [x] risk_engine.calculate_position_size() — real position sizing
  [x] Session filter            — no Asian session trades
  [x] Per-pair cooldown + shared max-trades/day cap (run_combined only)
  [x] Shared account balance across pairs (run_combined only)
  [ ] GPT-5.4 mini              — skipped (too slow + costs money)
                                   uses deterministic score only

Two simulation modes:
  run(pair, ...)          — single pair, its OWN independent starting
                             balance. Useful for isolated per-pair diagnosis,
                             but does NOT reflect a shared account: running
                             two pairs this way and summing results is
                             equivalent to trading $balance PER PAIR, not one
                             shared $balance account.
  run_combined(pairs, ...) — ALL pairs simulated together on a shared
                             account balance, a shared max-trades-per-day
                             cap, and per-pair cooldowns — this is what
                             actually reflects live trading_orchestrator.py
                             behavior (one MT5 account, risk_engine.
                             can_take_trade() gating every pair). Use this
                             for any "does the account hit $X/day" question.

Usage:
  python backtesting/replay_backtest.py                       # both pairs, combined/shared account
  python backtesting/replay_backtest.py --pair EURUSD --days 90   # single pair, isolated
"""

import sys
import argparse
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import json
import math
from datetime import datetime, timezone, timedelta

import pandas as pd
import numpy as np
import MetaTrader5 as mt5

from strategies.signal_engine import generate_signal, is_choppy_market
from strategies.indicators    import get_pip_value
from risk_management.risk_engine import RiskEngine
from core.config_manager import config
from core.session_manager import get_current_session
from core.logger import get_logger

logger = get_logger("replay_backtest")
PAIRS = ["EURUSD", "GBPUSD"]
REPORTS = ROOT / "storage" / "data"
FLAT_CLOSE_CUTOVER_UTC_HOUR = 21  # matches config.risk.flat_close_cutover_utc

# Mirrors news_engine/news_filter.py's RECURRING_MAJOR_EVENTS fallback
# schedule — duplicated here (rather than imported) specifically to avoid
# instantiating that module's NewsFilter() singleton, which fires live
# network calls (fxstreet/investing.com) at import time. This backtest only
# ever uses the static recurring-time fallback anyway (no historical,
# point-in-time economic-calendar dataset is available offline), so this is
# a faithful, network-free representation of that fallback behavior only —
# it is a fixed weekly schedule approximation, NOT date-accurate (e.g. it
# treats every day's 18:00 UTC as a "Fed decision," not just actual FOMC
# days), exactly like the live fallback it mirrors.
RECURRING_MAJOR_EVENTS = [
    (12, 30, "USD"), (13, 30, "USD"), (14, 0, "USD"), (18, 0, "USD"), (18, 30, "USD"),
    (7, 0, "GBP"), (9, 30, "GBP"),
    (8, 55, "EUR"), (9, 0, "EUR"), (12, 45, "EUR"), (13, 30, "EUR"),
]
NEWS_CURRENCY_PAIRS = {
    "USD": ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDJPY"],
    "GBP": ["GBPUSD", "GBPJPY", "EURGBP"],
    "EUR": ["EURUSD", "EURJPY", "EURGBP"],
}


def is_news_blackout(ts, pair: str, before_min: int = 20, after_min: int = 15) -> bool:
    """Pure, network-free check against the recurring-event fallback schedule."""
    affected = [c for c, pairs in NEWS_CURRENCY_PAIRS.items() if pair.upper() in pairs]
    if not affected:
        return False
    for hour, minute, currency in RECURRING_MAJOR_EVENTS:
        if currency not in affected:
            continue
        event_time = ts.replace(hour=hour, minute=minute, second=0, microsecond=0)
        diff_min = (ts - event_time).total_seconds() / 60
        if -before_min <= diff_min <= after_min:
            return True
    return False


def fetch_candles(pair: str, timeframe, days: int) -> pd.DataFrame:
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    rates = mt5.copy_rates_range(pair, timeframe, start, end)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    df.rename(columns={"tick_volume": "volume"}, inplace=True)
    return df


def is_session_allowed(ts) -> bool:
    """Only London + NY session: 07:00-20:00 UTC."""
    h = ts.hour
    return 7 <= h < 20 and not (12 <= h < 13)  # exclude dead zone


def max_consec(values, target):
    best = cur = 0
    for v in values:
        cur = cur + 1 if v == target else 0
        best = max(best, cur)
    return best


def _htf_slice(df_htf, ts, n=100):
    if df_htf is None:
        return None
    sub = df_htf[df_htf.index <= ts]
    return sub.iloc[-n:].copy() if len(sub) >= 20 else None


class ReplayBacktest:
    def __init__(self, initial_balance=500.0, spread_pips=1.5, commission_per_lot=3.5,
                 daily_targets=None, min_confidence=75.0, avoid_news=False,
                 cooldown_mult=1.0, max_trades_per_day=None, fixed_lot=None):
        self.initial_balance    = initial_balance
        self.spread_pips        = spread_pips
        self.commission_per_lot = commission_per_lot
        self.daily_targets      = daily_targets or [100.0]
        self.min_confidence     = min_confidence
        self.avoid_news         = avoid_news
        self.fixed_lot          = fixed_lot
        self.risk_engine        = RiskEngine()

        self.cooldown_std = (config.get("trading", "trade_cooldown_minutes") or 30) * cooldown_mult
        self.cooldown_high = (config.get("trading", "trade_cooldown_high_score_minutes") or 15) * cooldown_mult
        self.cooldown_high_threshold = config.get("trading", "cooldown_high_score_threshold") or 85
        self.max_trades_per_day = (
            max_trades_per_day if max_trades_per_day is not None
            else (config.get("trading", "max_trades_per_day") or 8)
        )

    # ------------------------------------------------------------------
    # Shared entry-decision logic — used by both run() and run_combined()
    # ------------------------------------------------------------------
    def _try_open_position(self, pair, df, i, ts, balance, df_h1, df_h4, df_d1):
        """
        Runs the real signal engine + real risk-engine SL/TP + real position
        sizing for one pair at one bar. Returns (position_dict, skip_reason);
        position_dict is None when no trade is taken.
        """
        pip_v = get_pip_value(pair)

        if self.avoid_news and is_news_blackout(ts, pair):
            return None, "news_blackout"

        m15_slice = df.iloc[max(0, i - 200): i + 1].copy()
        data_by_tf = {
            "M15": m15_slice,
            "H1":  _htf_slice(df_h1, ts),
            "H4":  _htf_slice(df_h4, ts),
            "D1":  _htf_slice(df_d1, ts),
        }

        sig = generate_signal(data_by_tf, pair)
        direction = sig.get("signal_direction", "NEUTRAL")
        if direction == "NEUTRAL":
            return None, "no_signal"

        confidence = sig.get("confidence", 0)
        if confidence < self.min_confidence:
            return None, "no_signal"

        entry   = sig.get("entry_price", df.iloc[i]["close"])
        trigger = sig.get("trigger", "")

        atr_series = (df.iloc[max(0, i - 14):i + 1]["high"] -
                      df.iloc[max(0, i - 14):i + 1]["low"]).mean()
        atr_pips = atr_series / pip_v

        session_label = get_current_session(ts).value
        sl, tp = self.risk_engine.calculate_sl_tp(
            pair, direction, entry, atr_pips, self.spread_pips,
            confidence_score=confidence, session=session_label,
        )

        sl_p = abs(entry - sl) / pip_v
        tp_p = abs(tp - entry) / pip_v
        if sl_p <= 0 or tp_p / sl_p < 1.45:
            return None, "rr_fail"

        if self.fixed_lot:
            lot = self.fixed_lot
        else:
            lot = self.risk_engine.calculate_position_size(balance, sl_p, pair, confidence)
            lot = max(0.01, min(0.20, lot))

        return {
            "direction": direction, "open": entry,
            "sl": sl, "sl_orig": sl, "tp": tp,
            "lot": lot, "be": False, "p1": False,
            "trigger": trigger, "open_time": ts, "confidence": confidence,
        }, None

    def _manage_position(self, pos, pair, bar, ts, pip_v):
        """Checks exits for one open position at one bar. Returns (closed_trade_dict|None)."""
        d, sl, tp, op, lot = pos["direction"], pos["sl"], pos["tp"], pos["open"], pos["lot"]
        hi, lo = bar["high"], bar["low"]
        close_price = exit_reason = None

        if ts.hour >= FLAT_CLOSE_CUTOVER_UTC_HOUR:
            close_price, exit_reason = bar["close"], "flat_close_cutover"
        elif d == "BUY":
            if lo <= sl: close_price, exit_reason = sl, "sl_hit"
            elif hi >= tp: close_price, exit_reason = tp, "tp_hit"
            else:
                if not pos["be"] and hi >= op + (tp - op) * 0.5:
                    pos["sl"] = round(op + self.spread_pips * pip_v, 5); pos["be"] = True
                if not pos["p1"] and hi >= op + (tp - op) * 0.99:
                    pos["lot"] = round(lot * 0.67, 2); pos["p1"] = True
        else:
            if hi >= sl: close_price, exit_reason = sl, "sl_hit"
            elif lo <= tp: close_price, exit_reason = tp, "tp_hit"
            else:
                if not pos["be"] and lo <= op - (op - tp) * 0.5:
                    pos["sl"] = round(op - self.spread_pips * pip_v, 5); pos["be"] = True
                if not pos["p1"] and lo <= op - (op - tp) * 0.99:
                    pos["lot"] = round(lot * 0.67, 2); pos["p1"] = True

        if close_price is None:
            return None

        raw_pips = (close_price - op) / pip_v if d == "BUY" else (op - close_price) / pip_v
        profit = raw_pips * pos["lot"] * 10
        profit -= self.commission_per_lot * pos["lot"]
        bars_held = round((ts - pos["open_time"]).total_seconds() / 900)
        return {
            "pair": pair, "direction": d, "open": op, "close": close_price,
            "sl": pos["sl_orig"], "tp": tp, "pips": round(raw_pips, 1),
            "profit": round(profit, 2), "exit": exit_reason, "lot": pos["lot"],
            "trigger": pos.get("trigger", ""), "be_moved": pos["be"],
            "bars_held": bars_held, "open_time": pos["open_time"], "close_time": ts,
        }

    # ------------------------------------------------------------------
    # Single-pair, independent-balance simulation (isolated diagnosis)
    # ------------------------------------------------------------------
    def run(self, pair: str, df_m15: pd.DataFrame,
            df_h1=None, df_h4=None, df_d1=None,
            warmup: int = 100) -> dict:

        pip_v     = get_pip_value(pair)
        balance   = self.initial_balance
        peak      = balance
        max_dd    = 0.0
        position  = None
        trades    = []
        equity    = [balance]
        skipped   = {"no_signal": 0, "rr_fail": 0, "cooldown": 0, "daily_cap": 0, "news_blackout": 0}
        last_close_time = None
        last_close_score = None
        daily_trade_count = {}

        total_bars = len(df_m15)
        print(f"    Replaying {total_bars} bars...", end="", flush=True)

        for i in range(warmup, total_bars):
            bar    = df_m15.iloc[i]
            bar_ts = df_m15.index[i]
            day    = bar_ts.date()
            daily_trade_count.setdefault(day, 0)

            if position:
                closed = self._manage_position(position, pair, bar, bar_ts, pip_v)
                if closed:
                    balance += closed["profit"]
                    trades.append(closed)
                    last_close_time = bar_ts
                    last_close_score = position.get("confidence", 70)
                    position = None
                    if balance > peak: peak = balance
                    max_dd = max(max_dd, (peak - balance) / peak * 100)

            if position is None and is_session_allowed(bar_ts):
                if daily_trade_count[day] >= self.max_trades_per_day:
                    skipped["daily_cap"] += 1
                    equity.append(balance)
                    continue
                if last_close_time is not None:
                    elapsed_min = (bar_ts - last_close_time).total_seconds() / 60
                    cd = self.cooldown_high if (last_close_score or 0) >= self.cooldown_high_threshold else self.cooldown_std
                    if elapsed_min < cd:
                        skipped["cooldown"] += 1
                        equity.append(balance)
                        continue

                position, skip_reason = self._try_open_position(
                    pair, df_m15, i, bar_ts, balance, df_h1, df_h4, df_d1
                )
                if position is None:
                    skipped[skip_reason] = skipped.get(skip_reason, 0) + 1
                else:
                    daily_trade_count[day] += 1

            equity.append(balance)

        if position:
            last = df_m15.iloc[-1]["close"]
            pips = (last - position["open"]) / pip_v
            if position["direction"] == "SELL": pips = -pips
            profit = pips * position["lot"] * 10
            balance += profit
            trades.append({**position, "pair": pair, "close": last, "pips": round(pips, 1),
                           "profit": round(profit, 2), "exit": "end_of_data",
                           "close_time": df_m15.index[-1]})

        print(" Done")
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        metrics = self._metrics(trades, equity, balance, max_dd, skipped, pair)
        return metrics, trades_df

    # ------------------------------------------------------------------
    # Multi-pair, SHARED-balance simulation — the faithful "one account"
    # view. Interleaves all pairs on a shared time axis with a shared
    # max-trades-per-day cap and per-pair cooldowns, mirroring
    # trading_orchestrator.py + risk_engine.can_take_trade() exactly.
    # ------------------------------------------------------------------
    def run_combined(self, pairs: list, data: dict, warmup: int = 100) -> dict:
        master_index = None
        for p in pairs:
            idx = data[p]["M15"].index
            master_index = idx if master_index is None else master_index.intersection(idx)
        master_index = master_index.sort_values()

        df_m15 = {p: data[p]["M15"] for p in pairs}
        df_h1  = {p: data[p].get("H1")  for p in pairs}
        df_h4  = {p: data[p].get("H4")  for p in pairs}
        df_d1  = {p: data[p].get("D1")  for p in pairs}
        pip_v  = {p: get_pip_value(p) for p in pairs}
        pos_by_pair       = {p: None for p in pairs}
        loc_cache         = {p: {ts: k for k, ts in enumerate(df_m15[p].index)} for p in pairs}
        last_close_time   = {p: None for p in pairs}
        last_close_score  = {p: None for p in pairs}

        balance = self.initial_balance
        peak    = balance
        max_dd  = 0.0
        trades  = []
        equity  = [balance]
        skipped = {"no_signal": 0, "rr_fail": 0, "cooldown": 0, "daily_cap": 0, "news_blackout": 0}
        daily_trade_count = {}

        total = len(master_index)
        print(f"    Replaying {total} shared bars across {pairs}...", end="", flush=True)

        for ts in master_index[warmup:]:
            day = ts.date()
            daily_trade_count.setdefault(day, 0)

            for p in pairs:
                i = loc_cache[p].get(ts)
                if i is None:
                    continue
                bar = df_m15[p].iloc[i]
                pos = pos_by_pair[p]

                if pos:
                    closed = self._manage_position(pos, p, bar, ts, pip_v[p])
                    if closed:
                        balance += closed["profit"]
                        trades.append(closed)
                        last_close_time[p] = ts
                        last_close_score[p] = pos.get("confidence", 70)
                        pos_by_pair[p] = None
                        if balance > peak: peak = balance
                        max_dd = max(max_dd, (peak - balance) / peak * 100)
                    continue  # a pair with an open (or just-closed) position doesn't also open a new one this bar

                if not is_session_allowed(ts):
                    continue
                if daily_trade_count[day] >= self.max_trades_per_day:
                    skipped["daily_cap"] += 1
                    continue
                if last_close_time[p] is not None:
                    elapsed_min = (ts - last_close_time[p]).total_seconds() / 60
                    cd = self.cooldown_high if (last_close_score[p] or 0) >= self.cooldown_high_threshold else self.cooldown_std
                    if elapsed_min < cd:
                        skipped["cooldown"] += 1
                        continue

                new_pos, skip_reason = self._try_open_position(
                    p, df_m15[p], i, ts, balance, df_h1[p], df_h4[p], df_d1[p]
                )
                if new_pos is None:
                    skipped[skip_reason] = skipped.get(skip_reason, 0) + 1
                else:
                    pos_by_pair[p] = new_pos
                    daily_trade_count[day] += 1

            equity.append(balance)

        for p in pairs:
            pos = pos_by_pair[p]
            if pos:
                last = df_m15[p].iloc[-1]["close"]
                pips = (last - pos["open"]) / pip_v[p]
                if pos["direction"] == "SELL": pips = -pips
                profit = pips * pos["lot"] * 10
                balance += profit
                trades.append({**pos, "pair": p, "close": last, "pips": round(pips, 1),
                               "profit": round(profit, 2), "exit": "end_of_data",
                               "close_time": df_m15[p].index[-1]})

        print(" Done")
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        metrics = self._metrics(trades, equity, balance, max_dd, skipped, "COMBINED")
        return metrics, trades_df

    def _metrics(self, trades, equity, final_balance, max_dd, skipped, pair):
        if not trades:
            print(f"  Skipped: {skipped}"); return {"error": "No trades", "pair": pair, "skipped": skipped}

        df = pd.DataFrame(trades)
        wins   = df[df["profit"] > 0]
        losses = df[df["profit"] <= 0]
        total  = len(df)
        wr     = len(wins) / total * 100
        gp     = wins["profit"].sum() if not wins.empty else 0
        gl     = abs(losses["profit"].sum()) if not losses.empty else 0
        net    = df["profit"].sum()
        pf     = gp / max(gl, 0.01)
        avg_w  = wins["profit"].mean() if not wins.empty else 0
        avg_l  = losses["profit"].mean() if not losses.empty else 0
        exp    = (wr / 100 * avg_w) + ((1 - wr / 100) * avg_l)

        trig_perf = {}
        for trig, grp in df.groupby("trigger"):
            tw = grp[grp["profit"] > 0]
            trig_perf[trig] = {
                "trades": len(grp),
                "win_rate": round(len(tw) / len(grp) * 100, 1),
                "net": round(grp["profit"].sum(), 2),
            }

        ret = pd.Series(equity).pct_change().dropna()
        sharpe = (ret.mean() / max(ret.std(), 1e-6)) * math.sqrt(96 * 252)

        won_list = df["profit"].apply(lambda x: x > 0).tolist()
        max_loss_streak = max_consec(won_list, False)

        return {
            "pair": pair,
            "total_trades": total,
            "win_rate_pct": round(wr, 1),
            "net_profit": round(net, 2),
            "roi_pct": round(net / self.initial_balance * 100, 2),
            "profit_factor": round(pf, 2),
            "expectancy": round(exp, 2),
            "avg_win": round(avg_w, 2),
            "avg_loss": round(avg_l, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "max_loss_streak": max_loss_streak,
            "sl_hits": int(df["exit"].eq("sl_hit").sum()),
            "tp_hits": int(df["exit"].eq("tp_hit").sum()),
            "flat_close_cutover_exits": int(df["exit"].eq("flat_close_cutover").sum()),
            "flat_close_cutover_pct": round(df["exit"].eq("flat_close_cutover").mean() * 100, 1),
            "avg_bars_held": round(df["bars_held"].mean(), 1) if "bars_held" in df.columns else 0,
            "trigger_performance": trig_perf,
            "skipped": skipped,
            "final_balance": round(final_balance, 2),
            "daily": self._daily_metrics(df),
        }

    def _daily_metrics(self, df: pd.DataFrame) -> dict:
        """
        Groups closed trades by the UTC calendar date they closed on and
        computes day-by-day performance. The aggregate trade-level stats
        above (win rate, total net profit, ...) can't answer "does this hit
        $X/day" on their own — this is the breakdown that actually can.
        """
        if "close_time" not in df.columns or df["close_time"].isna().all():
            return {"available": False}

        d = df.dropna(subset=["close_time"]).copy()
        d["date"] = pd.to_datetime(d["close_time"]).dt.date
        daily = d.groupby("date")["profit"].sum().sort_index()
        n_days = len(daily)
        if n_days == 0:
            return {"available": False}

        is_loss_day = (daily < 0).tolist()
        max_losing_day_streak = max_consec(is_loss_day, True)

        targets = self.daily_targets or [100.0]
        target_stats = {}
        for t in targets:
            target_stats[t] = {
                "days_hit": int((daily >= t).sum()),
                "days_hit_pct": round((daily >= t).mean() * 100, 1),
            }

        primary = targets[0]
        return {
            "available": True,
            "n_trading_days": n_days,
            "daily_target_usd": primary,
            "days_hit_target": target_stats[primary]["days_hit"],
            "days_hit_target_pct": target_stats[primary]["days_hit_pct"],
            "targets": target_stats,
            "days_positive": int((daily > 0).sum()),
            "days_positive_pct": round((daily > 0).mean() * 100, 1),
            "days_negative": int((daily < 0).sum()),
            "days_negative_pct": round((daily < 0).mean() * 100, 1),
            "avg_daily_pnl": round(daily.mean(), 2),
            "median_daily_pnl": round(daily.median(), 2),
            "daily_pnl_std": round(daily.std(), 2) if n_days > 1 else 0.0,
            "best_day": round(daily.max(), 2),
            "worst_day": round(daily.min(), 2),
            "max_losing_day_streak": max_losing_day_streak,
        }


def print_daily_block(daily: dict, label: str = "DAILY PERFORMANCE") -> None:
    if not daily or not daily.get("available"):
        print(f"\n  {label}: not enough closed-trade timestamp data")
        return
    print(f"\n  {label}")
    print(f"  Trading days:           {daily['n_trading_days']}")
    for tgt, stats in sorted(daily.get("targets", {}).items()):
        print(f"  Days hitting ${tgt:.0f}/day:    {stats['days_hit']} / {daily['n_trading_days']} "
              f"({stats['days_hit_pct']:.1f}%)")
    print(f"  Days positive:          {daily['days_positive']} ({daily['days_positive_pct']:.1f}%)")
    print(f"  Days negative:          {daily['days_negative']} ({daily['days_negative_pct']:.1f}%)")
    print(f"  Avg daily P&L:          ${daily['avg_daily_pnl']:+.2f}")
    print(f"  Median daily P&L:       ${daily['median_daily_pnl']:+.2f}")
    print(f"  Daily P&L std dev:      ${daily['daily_pnl_std']:.2f}")
    print(f"  Best day:               ${daily['best_day']:+.2f}")
    print(f"  Worst day:              ${daily['worst_day']:+.2f}")
    print(f"  Max losing-day streak:  {daily['max_losing_day_streak']} days")


def print_results(r):
    if "error" in r:
        print(f"  X {r['pair']}: {r['error']}")
        return
    pf = r["profit_factor"]
    grade = "OK GOOD" if pf >= 1.5 and r["win_rate_pct"] >= 45 else \
            "!  MARGINAL" if pf >= 1.2 else "X POOR"

    print(f"\n{'-'*58}")
    print(f"  {r['pair']}  {grade}")
    print(f"{'-'*58}")
    print(f"  Trades:          {r['total_trades']}")
    print(f"  Win Rate:        {r['win_rate_pct']:.1f}%")
    print(f"  Net Profit:      ${r['net_profit']:.2f}  (ROI: {r['roi_pct']:.1f}%)")
    print(f"  Profit Factor:   {pf:.2f}  (>1.5 good)")
    print(f"  Expectancy:      ${r['expectancy']:.2f} per trade")
    print(f"  Max Drawdown:    {r['max_drawdown_pct']:.1f}%")
    print(f"  Sharpe Ratio:    {r['sharpe_ratio']:.2f}")
    print(f"  Avg Win:         ${r['avg_win']:.2f}")
    print(f"  Avg Loss:        ${r['avg_loss']:.2f}")
    print(f"  Max Loss Streak: {r['max_loss_streak']} trades")
    sl, tp = r["sl_hits"], r["tp_hits"]
    tot = sl + tp
    if tot > 0:
        print(f"  SL hits:         {sl} ({sl/tot*100:.0f}%)")
        print(f"  TP hits:         {tp} ({tp/tot*100:.0f}%)")
    print(f"  Flat-close exits: {r['flat_close_cutover_exits']} ({r['flat_close_cutover_pct']:.1f}% of trades)")
    print(f"  Avg bars held:   {r['avg_bars_held']} bars (~{r['avg_bars_held']*15/60:.1f}h)")
    print_daily_block(r.get("daily"), label=f"DAILY PERFORMANCE ({r['pair']})")
    sk = r["skipped"]
    total_sk = sum(sk.values())
    print(f"\n  Skipped: {total_sk} signals")
    for reason, count in sk.items():
        if count > 0:
            print(f"    {reason}: {count}")
    print(f"\n  Top triggers:")
    for trig, stats in sorted(r["trigger_performance"].items(),
                               key=lambda x: x[1]["net"], reverse=True)[:5]:
        print(f"    {trig}: {stats['trades']} trades | WR={stats['win_rate']}% | Net=${stats['net']:.2f}")


def print_pair_breakdown(trades_df: pd.DataFrame) -> None:
    if trades_df.empty or "pair" not in trades_df.columns:
        return
    print(f"\n  Per-pair contribution (shared account):")
    for pair, grp in trades_df.groupby("pair"):
        wins = grp[grp["profit"] > 0]
        wr = len(wins) / len(grp) * 100 if len(grp) else 0
        print(f"    {pair}: {len(grp)} trades | WR={wr:.1f}% | Net=${grp['profit'].sum():.2f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair",    default=None,
                         help="Run ONE pair in isolation with its OWN independent balance "
                              "(diagnostic). Omit to run all pairs together on one SHARED "
                              "account balance (the faithful 'does the account hit $X/day' view).")
    parser.add_argument("--days",    type=int, default=90)
    parser.add_argument("--balance", type=float, default=500.0)
    parser.add_argument("--spread",  type=float, default=1.5)
    parser.add_argument("--daily-target", type=str, default="100",
                         help="Daily P&L target(s) in USD, comma-separated for multiple "
                              "(e.g. '15,20,30') — all evaluated from the SAME simulated "
                              "trade sequence in one pass")
    parser.add_argument("--risk-mult", type=float, default=1.0,
                         help="Scale the risk_pct_* config tiers by this factor for THIS "
                              "run only (in-process; never writes to config.json)")
    parser.add_argument("--min-confidence", type=float, default=75.0,
                         help="Minimum signal_engine confidence score required to take a "
                              "trade (default 75, matching the live bot's marginal-zone floor)")
    parser.add_argument("--cooldown-mult", type=float, default=1.0,
                         help="Scale the per-pair cooldown minutes by this factor "
                              "(e.g. 0.5 = half the cooldown = more trade frequency)")
    parser.add_argument("--max-trades-per-day", type=int, default=None,
                         help="Override config.trading.max_trades_per_day (shared cap "
                              "across all pairs in --mode combined)")
    parser.add_argument("--fixed-lot", type=float, default=None,
                         help="Use a FIXED lot size for every trade instead of dynamic "
                              "risk-based sizing (e.g. 0.1, 0.2, 0.3) — bypasses "
                              "calculate_position_size() entirely")
    parser.add_argument("--avoid-news", action="store_true",
                         help="Block new entries during the recurring major-news fallback "
                              "windows (NFP/CPI/Fed/ECB/BOE approximate UTC times)")
    args = parser.parse_args()

    pairs = [args.pair.upper()] if args.pair else PAIRS
    daily_targets = [float(x) for x in args.daily_target.split(",")]

    if args.risk_mult != 1.0:
        for key in ("risk_pct_cautious", "risk_pct_standard", "risk_pct_high"):
            original = config.get("risk", key)
            config._config["risk"][key] = original * args.risk_mult
        print(f"  [risk-mult] Scaled risk_pct tiers by {args.risk_mult}x for this run "
              f"only (config.json untouched) -> "
              f"{config.get('risk','risk_pct_cautious')}/"
              f"{config.get('risk','risk_pct_standard')}/"
              f"{config.get('risk','risk_pct_high')}")

    print(f"\n{'='*58}")
    print(f"  ForexAI REAL Strategy Replay - {args.days} days")
    print(f"  Balance: ${args.balance} | Spread: {args.spread}p | "
          f"Daily target(s): {', '.join(f'${t:.0f}' for t in daily_targets)}")
    print(f"  Min confidence: {args.min_confidence} | Cooldown mult: {args.cooldown_mult} | "
          f"Max trades/day: {args.max_trades_per_day or 'config default'} | "
          f"Fixed lot: {args.fixed_lot or 'dynamic'} | Avoid news: {args.avoid_news}")
    print(f"  Uses: signal_engine + risk_engine (real SL/TP + sizing) + session filter")
    print(f"  Skips: GPT evaluation (deterministic only)")
    print(f"{'='*58}")

    if not mt5.initialize():
        print("X MT5 not connected")
        return

    engine = ReplayBacktest(
        args.balance, args.spread, daily_targets=daily_targets,
        min_confidence=args.min_confidence, avoid_news=args.avoid_news,
        cooldown_mult=args.cooldown_mult, max_trades_per_day=args.max_trades_per_day,
        fixed_lot=args.fixed_lot,
    )

    pair_data = {}
    for pair in pairs:
        print(f"\n  Fetching {pair}...")
        df_m15 = fetch_candles(pair, mt5.TIMEFRAME_M15, args.days)
        df_h1  = fetch_candles(pair, mt5.TIMEFRAME_H1,  args.days)
        df_h4  = fetch_candles(pair, mt5.TIMEFRAME_H4,  args.days)
        df_d1  = fetch_candles(pair, mt5.TIMEFRAME_D1,  args.days + 30)
        if df_m15 is None:
            print(f"  X No data for {pair}")
            continue
        print(f"    M15:{len(df_m15)} H1:{len(df_h1) if df_h1 is not None else 0} "
              f"H4:{len(df_h4) if df_h4 is not None else 0} "
              f"D1:{len(df_d1) if df_d1 is not None else 0} bars")
        pair_data[pair] = {"M15": df_m15, "H1": df_h1, "H4": df_h4, "D1": df_d1}

    if not pair_data:
        print("X No data for any pair")
        mt5.shutdown()
        return

    if args.pair:
        # Single-pair isolated diagnostic run (its own independent balance).
        pd_ = pair_data[args.pair.upper()]
        r, trades_df = engine.run(args.pair.upper(), pd_["M15"], pd_["H1"], pd_["H4"], pd_["D1"])
        print_results(r)
        report = REPORTS / f"replay_{args.pair.upper()}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(report, "w") as f:
            json.dump(r, f, indent=2, default=str)
    else:
        # Combined, shared-account run across all pairs — the faithful view.
        print(f"\n  Running COMBINED shared-account simulation across {list(pair_data.keys())}...")
        r, trades_df = engine.run_combined(list(pair_data.keys()), pair_data)
        print_results(r)
        print_pair_breakdown(trades_df)
        report = REPORTS / f"replay_COMBINED_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(report, "w") as f:
            json.dump(r, f, indent=2, default=str)

    mt5.shutdown()


if __name__ == "__main__":
    main()
