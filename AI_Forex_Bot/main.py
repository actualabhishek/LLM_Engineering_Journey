#!/usr/bin/env python3
"""
main.py — ForexAI Trader Entry Point
=====================================
The trading_orchestrator.run_system() function manages the full lifecycle:
  MT5 connection → trade monitor → autonomous scanner → webhook server.

This file adds CLI argument parsing and the extra --mode options
(dashboard, backtest, webhook-only) on top of that.

Usage:
    python main.py                   # full production mode
    python main.py --dry-run         # simulation, no real orders
    python main.py --mode webhook    # webhook server only
    python main.py --mode backtest   # backtester, then exit
    python main.py --mode dashboard  # Streamlit dashboard
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


# ── mode handlers ─────────────────────────────────────────────────────────────

def run_full_system(dry_run: bool = False) -> None:
    """Full production mode — delegates to the orchestrator's run_system()."""
    if dry_run:
        os.environ["SIMULATION_MODE"] = "true"
        print("[INFO] DRY-RUN mode — no real orders will be placed.")

    from trading_orchestrator import run_system
    run_system()


def run_webhook_only() -> None:
    """Webhook server only — useful for testing TradingView alerts."""
    import uvicorn
    from core.config_manager import config
    host = config.get("webhook", "host") or "0.0.0.0"
    port = config.get("webhook", "port") or 8000
    print(f"[INFO] Webhook server starting on {host}:{port}")
    uvicorn.run(
        "tradingview_webhook.webhook_server:app",
        host=host,
        port=int(port),
        log_level="info",
    )


def run_backtest(pair: str = None, days: int = 90, balance: float = 500.0, spread: float = 1.5,
                  daily_target: str = "100", risk_mult: float = 1.0,
                  min_confidence: float = None, cooldown_mult: float = None,
                  max_trades_per_day: int = None, fixed_lot: float = None,
                  avoid_news: bool = False) -> None:
    """
    Run the REAL strategy backtester (backtesting/replay_backtest.py) —
    replays live MT5 history through the actual signal_engine/risk_engine,
    unlike the old simplified backtest_engine.py (see run_legacy_backtest).

    `daily_target` accepts a comma-separated list (e.g. "15,20,30") to
    evaluate multiple daily targets from one simulation pass. Omitting
    `pair` runs ALL pairs together on one shared account balance (the
    faithful "does the account hit $X/day" view) instead of one pair in
    isolation.
    """
    script = ROOT / "backtesting" / "replay_backtest.py"
    cmd = [sys.executable, str(script), "--days", str(days), "--balance", str(balance),
           "--spread", str(spread), "--daily-target", str(daily_target),
           "--risk-mult", str(risk_mult)]
    if pair:
        cmd += ["--pair", pair]
    if min_confidence is not None:
        cmd += ["--min-confidence", str(min_confidence)]
    if cooldown_mult is not None:
        cmd += ["--cooldown-mult", str(cooldown_mult)]
    if max_trades_per_day is not None:
        cmd += ["--max-trades-per-day", str(max_trades_per_day)]
    if fixed_lot is not None:
        cmd += ["--fixed-lot", str(fixed_lot)]
    if avoid_news:
        cmd += ["--avoid-news"]
    print("[INFO] Running real-strategy replay backtest (signal_engine + risk_engine)...")
    subprocess.run(cmd, check=False)


def run_legacy_backtest() -> None:
    """
    Run the OLD simplified backtester. Tests a strategy that is no longer
    live (a different, simpler rule set than strategies/signal_engine.py) —
    kept only for historical reference, NOT representative of the real bot.
    Use --mode backtest for a faithful result.
    """
    from backtesting.backtest_engine import BacktestEngine
    print("[INFO] Starting legacy backtest (simplified strategy — not representative of the live bot)...")
    engine = BacktestEngine()
    results = engine.run()
    print("\n" + "=" * 44)
    print("  LEGACY BACKTEST RESULTS")
    print("=" * 44)
    for key, val in results.get("metrics", {}).items():
        print(f"  {key:<28}: {val}")
    print("=" * 44)
    if results.get("report_path"):
        print(f"\n  Full report saved → {results['report_path']}")


def run_dashboard() -> None:
    """Launch the Streamlit live dashboard."""
    dashboard_path = ROOT / "dashboard" / "app.py"
    print(f"[INFO] Launching dashboard — open http://localhost:8501")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(dashboard_path),
         "--server.headless", "true"],
        check=False,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ForexAI Trader — AI-powered autonomous forex trading system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  full             Full production system (default)
  webhook          Webhook server only
  backtest         Run the REAL strategy replay backtest and exit
  legacy-backtest  Run the old simplified backtester (not representative)
  dashboard        Launch Streamlit dashboard

Examples:
  python main.py
  python main.py --dry-run
  python main.py --mode backtest --pair EURUSD --days 90
  python main.py --mode dashboard
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["full", "webhook", "backtest", "legacy-backtest", "dashboard"],
        default="full",
        help="Operating mode (default: full)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulation mode — no real MT5 orders placed",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to alternate config.json",
    )
    parser.add_argument("--pair", default=None, help="[backtest mode] pair to test, e.g. EURUSD")
    parser.add_argument("--days", type=int, default=90, help="[backtest mode] days of history")
    parser.add_argument("--balance", type=float, default=500.0, help="[backtest mode] starting balance")
    parser.add_argument("--spread", type=float, default=1.5, help="[backtest mode] spread in pips")
    parser.add_argument("--daily-target", type=str, default="100",
                         help="[backtest mode] daily P&L target(s) in USD, comma-separated "
                              "for multiple (e.g. '15,20,100')")
    parser.add_argument("--risk-mult", type=float, default=1.0,
                         help="[backtest mode] scale risk_pct_* tiers by this factor, "
                              "in-process only (config.json untouched)")
    args = parser.parse_args()

    if args.config:
        os.environ["CONFIG_PATH"] = args.config

    if args.mode == "full":
        run_full_system(dry_run=args.dry_run)
    elif args.mode == "webhook":
        run_webhook_only()
    elif args.mode == "backtest":
        run_backtest(pair=args.pair, days=args.days, balance=args.balance, spread=args.spread,
                     daily_target=args.daily_target, risk_mult=args.risk_mult)
    elif args.mode == "legacy-backtest":
        run_legacy_backtest()
    elif args.mode == "dashboard":
        run_dashboard()


if __name__ == "__main__":
    main()
