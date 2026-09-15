"""
run_backtest.py
---------------
Run backtests on your ForexAI strategy using MT5 historical data.

Usage:
  python run_backtest.py                    # backtest all pairs, 6 months
  python run_backtest.py --pair EURUSD      # single pair
  python run_backtest.py --days 90          # last 90 days
  python run_backtest.py --pair EURUSD --days 180 --balance 500
"""

import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from datetime import datetime, timezone, timedelta
import pandas as pd
import MetaTrader5 as mt5

from core.config_manager import config
from backtesting.backtest_engine import BacktestEngine
from core.logger import get_logger

logger = get_logger("backtest")

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "EURJPY", "GBPJPY"]


def fetch_mt5_data(pair: str, days: int = 180) -> pd.DataFrame:
    """Fetch historical M15 candles from MT5."""
    if not mt5.initialize():
        print("❌ MT5 not connected — open MT5 first")
        return None

    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    rates = mt5.copy_rates_range(pair, mt5.TIMEFRAME_M15, start, end)
    if rates is None or len(rates) == 0:
        print(f"❌ No data for {pair}")
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df.rename(columns={"tick_volume": "volume"}, inplace=True)
    print(f"✓ {pair}: {len(df)} M15 bars ({days} days)")
    return df


def print_results(results: dict, pair: str):
    """Print formatted backtest results."""
    if "error" in results:
        print(f"  ❌ {pair}: {results['error']}")
        return

    pf    = results["profit_factor"]
    wr    = results["win_rate_pct"]
    net   = results["net_profit"]
    dd    = results["max_drawdown_pct"]
    sh    = results["sharpe_ratio"]
    roi   = results["roi_pct"]
    total = results["total_trades"]
    exp   = results["expectancy"]

    # Grade the strategy
    if pf >= 1.5 and wr >= 45 and dd <= 15:
        grade = "✅ GOOD"
    elif pf >= 1.2 and wr >= 40:
        grade = "⚠️  MARGINAL"
    else:
        grade = "❌ POOR"

    print(f"\n{'─'*55}")
    print(f"  {pair}  {grade}")
    print(f"{'─'*55}")
    print(f"  Trades:         {total}")
    print(f"  Win Rate:       {wr:.1f}%")
    print(f"  Net Profit:     ${net:.2f}")
    print(f"  ROI:            {roi:.1f}%")
    print(f"  Profit Factor:  {pf:.2f}  (>1.5 = good)")
    print(f"  Expectancy:     ${exp:.2f} per trade")
    print(f"  Max Drawdown:   {dd:.1f}%  (<15% = good)")
    print(f"  Sharpe Ratio:   {sh:.2f}  (>1.0 = good)")
    print(f"  Avg Win:        ${results['avg_win']:.2f}")
    print(f"  Avg Loss:       ${results['avg_loss']:.2f}")
    print(f"  Max Loss Streak:{results['max_consecutive_losses']} trades")
    exits = results.get("exit_reasons", {})
    if exits:
        sl = exits.get("sl_hit", 0)
        tp = exits.get("tp_hit", 0)
        total_ex = sl + tp
        if total_ex > 0:
            print(f"  SL hits:        {sl} ({sl/total_ex*100:.0f}%)")
            print(f"  TP hits:        {tp} ({tp/total_ex*100:.0f}%)")


def main():
    parser = argparse.ArgumentParser(description="ForexAI Backtest Runner")
    parser.add_argument("--pair",    default=None, help="Single pair (e.g. EURUSD)")
    parser.add_argument("--days",    type=int, default=180, help="History days (default 180)")
    parser.add_argument("--balance", type=float, default=500.0, help="Starting balance")
    parser.add_argument("--lot",     type=float, default=0.02, help="Fixed lot size")
    parser.add_argument("--spread",  type=float, default=1.5, help="Spread in pips")
    parser.add_argument("--monte",   action="store_true", help="Run Monte Carlo simulation")
    args = parser.parse_args()

    pairs = [args.pair.upper()] if args.pair else PAIRS

    print(f"\n{'='*55}")
    print(f"  ForexAI Backtest — {args.days} days history")
    print(f"  Balance: ${args.balance} | Lot: {args.lot} | Spread: {args.spread}p")
    print(f"  Pairs: {', '.join(pairs)}")
    print(f"{'='*55}")

    engine = BacktestEngine(
        initial_balance=args.balance,
        lot_size=args.lot,
        spread_pips=args.spread,
    )

    all_results = []
    for pair in pairs:
        df = fetch_mt5_data(pair, days=args.days)
        if df is None:
            continue

        print(f"\n  Running {pair}...", end=" ", flush=True)
        results = engine.run(df, pair)
        print(f"Done — {results.get('total_trades', 0)} trades")

        print_results(results, pair)
        all_results.append(results)

        # Monte Carlo if requested
        if args.monte and "total_trades" in results and results["total_trades"] > 20:
            import json
            report_path = list(Path("storage/data").glob(f"backtest_{pair}_*.json"))
            if report_path:
                with open(sorted(report_path)[-1]) as f:
                    trade_data = json.load(f)
            mc = engine.monte_carlo([{"profit": results["expectancy"]}] * results["total_trades"])
            print(f"\n  Monte Carlo ({mc['simulations']} simulations):")
            print(f"    Best case  (95th): ${mc['equity_95th_percentile']:.2f}")
            print(f"    Median:            ${mc['equity_median']:.2f}")
            print(f"    Worst case  (5th): ${mc['equity_5th_percentile']:.2f}")
            print(f"    Prob of profit:    {mc['probability_of_profit']:.0f}%")
            print(f"    Median max DD:     {mc['max_dd_median']:.1f}%")

    # Summary across all pairs
    if len(all_results) > 1:
        valid = [r for r in all_results if "net_profit" in r]
        print(f"\n{'='*55}")
        print(f"  PORTFOLIO SUMMARY")
        print(f"{'='*55}")
        total_profit = sum(r["net_profit"] for r in valid)
        avg_wr       = sum(r["win_rate_pct"] for r in valid) / len(valid)
        avg_pf       = sum(r["profit_factor"] for r in valid) / len(valid)
        avg_dd       = sum(r["max_drawdown_pct"] for r in valid) / len(valid)
        best  = max(valid, key=lambda r: r["net_profit"])
        worst = min(valid, key=lambda r: r["net_profit"])
        print(f"  Total P&L:      ${total_profit:.2f}")
        print(f"  Avg Win Rate:   {avg_wr:.1f}%")
        print(f"  Avg Prof Factor:{avg_pf:.2f}")
        print(f"  Avg Max DD:     {avg_dd:.1f}%")
        print(f"  Best pair:      {best['pair']} (${best['net_profit']:.2f})")
        print(f"  Worst pair:     {worst['pair']} (${worst['net_profit']:.2f})")
        print(f"\n  Reports saved to: storage/data/backtest_*.json")

    mt5.shutdown()


if __name__ == "__main__":
    main()
