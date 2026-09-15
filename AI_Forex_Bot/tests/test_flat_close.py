"""
tests/test_flat_close.py
-------------------------
Tests for the Iteration-1 exit-logic overhaul in mt5_execution/trade_monitor.py:
the strict same-day flat-close cutover that replaced the old "hold up to 24h,
exit early only if at breakeven/loss" behavior. This is the single highest-
value new test from that iteration since it's a live-trading-affecting
behavior change.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from mt5_execution.trade_monitor import TradeMonitor


def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 5, hour, minute, tzinfo=timezone.utc)


class TestPastFlatCloseCutover:
    def test_before_cutover_is_false(self):
        monitor = TradeMonitor()
        with patch("mt5_execution.trade_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = _utc(20, 59)
            assert monitor._past_flat_close_cutover() is False

    def test_at_cutover_is_true(self):
        monitor = TradeMonitor()
        with patch("mt5_execution.trade_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = _utc(21, 0)
            assert monitor._past_flat_close_cutover() is True

    def test_after_cutover_is_true(self):
        monitor = TradeMonitor()
        with patch("mt5_execution.trade_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = _utc(23, 30)
            assert monitor._past_flat_close_cutover() is True

    def test_early_morning_is_false(self):
        monitor = TradeMonitor()
        with patch("mt5_execution.trade_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = _utc(8, 0)
            assert monitor._past_flat_close_cutover() is False


class TestMonitorLoopForcesCloseAtCutover:
    def test_close_all_called_when_past_cutover_with_open_trades(self):
        """
        The single most important regression guard from Iteration 1: once
        wall-clock time passes the cutover, every open position must be
        force-closed regardless of P&L — this replaced the old hardcoded
        24h/breakeven-or-loss-only exit rule.
        """
        monitor = TradeMonitor()
        with patch.object(monitor, "_update_drawdown"), \
             patch.object(monitor, "_past_flat_close_cutover", return_value=True), \
             patch("mt5_execution.trade_monitor.is_kill_switch_active", return_value=False), \
             patch("mt5_execution.trade_monitor.get_active_trades",
                   return_value={"111": {"pair": "EURUSD", "direction": "BUY"}}), \
             patch.object(monitor, "_close_all") as mock_close_all, \
             patch.object(monitor, "_check_all_trades") as mock_check_all:

            # Run one iteration of the loop body directly (avoid the
            # infinite while loop / real time.sleep).
            monitor._running = True

            def stop_after_one_cycle(*args, **kwargs):
                monitor._running = False

            with patch("mt5_execution.trade_monitor.time.sleep", side_effect=stop_after_one_cycle):
                monitor._monitor_loop()

            mock_close_all.assert_called_once_with("flat_close_cutover")
            mock_check_all.assert_not_called()

    def test_normal_management_runs_when_not_past_cutover(self):
        monitor = TradeMonitor()
        with patch.object(monitor, "_update_drawdown"), \
             patch.object(monitor, "_past_flat_close_cutover", return_value=False), \
             patch("mt5_execution.trade_monitor.is_kill_switch_active", return_value=False), \
             patch.object(monitor, "_close_all") as mock_close_all, \
             patch.object(monitor, "_check_all_trades") as mock_check_all:

            monitor._running = True

            def stop_after_one_cycle(*args, **kwargs):
                monitor._running = False

            with patch("mt5_execution.trade_monitor.time.sleep", side_effect=stop_after_one_cycle):
                monitor._monitor_loop()

            mock_close_all.assert_not_called()
            mock_check_all.assert_called_once()
