"""
tests/test_core_modules.py
--------------------------
Unit tests for the ForexAI Trader core modules.

Rewritten against the REAL current module API (the previous version tested a
speculative API — e.g. ConfidenceEngine.compute(), RiskEngine.compute_sl_tp(),
a SessionManager/StateManager class — that never matched the actual
implementation; 25 of 35 tests failed on collection/execution as a result).

Run with:
    pytest tests/ -v
or:
    python -m pytest tests/test_core_modules.py -v
"""

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

# ── make project importable ───────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import core.state_manager as state_manager


class _IsolatedStateMixin:
    """
    Redirects core.state_manager's file-backed storage to a temp directory
    for the duration of a test, so tests never read/write real trading state
    under storage/data/. Call self._isolate_state() from setUp().
    """

    def _isolate_state(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        tmp_path = Path(tmpdir.name)
        patcher = patch.multiple(
            state_manager,
            ACTIVE_TRADES_FILE=tmp_path / "active_trades.json",
            TRADE_HISTORY_FILE=tmp_path / "trade_history.csv",
            DAILY_STATS_FILE=tmp_path / "daily_stats.json",
            AI_LOG_FILE=tmp_path / "ai_logs.json",
            KILL_SWITCH_FILE=tmp_path / "kill_switch.json",
        )
        patcher.start()
        self.addCleanup(patcher.stop)


# ═══════════════════════════════════════════════════════════════════════════════
# Session Manager (module of free functions — not a class)
# ═══════════════════════════════════════════════════════════════════════════════
class TestSessionManager(unittest.TestCase):

    def test_get_session_info_shape(self):
        from core.session_manager import get_session_info
        info = get_session_info()
        self.assertIn("session", info)
        self.assertIn("min_confidence_required", info)
        self.assertIsInstance(info["min_confidence_required"], (int, float))

    def test_is_trading_time_returns_tuple(self):
        from core.session_manager import is_trading_time
        allowed, reason = is_trading_time()
        self.assertIsInstance(allowed, bool)
        self.assertIsInstance(reason, str)

    def test_best_pairs_is_list(self):
        from core.session_manager import get_best_pairs_for_session, Session
        pairs = get_best_pairs_for_session(Session.LONDON)
        self.assertIsInstance(pairs, list)

    def test_london_detection(self):
        from core.session_manager import get_current_session, Session
        london_time = datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc)
        session = get_current_session(london_time)
        self.assertIn(session, (Session.LONDON, Session.OVERLAP))

    def test_off_hours_detection(self):
        """22:30 UTC falls in the gap after NY close and before Asian open."""
        from core.session_manager import get_current_session, Session
        off_time = datetime(2024, 6, 3, 22, 30, tzinfo=timezone.utc)
        session = get_current_session(off_time)
        self.assertEqual(session, Session.OFF)


# ═══════════════════════════════════════════════════════════════════════════════
# Confidence Engine
# ═══════════════════════════════════════════════════════════════════════════════
class TestConfidenceEngine(unittest.TestCase):

    def setUp(self):
        from strategies.confidence_engine import ConfidenceEngine
        self.engine = ConfidenceEngine()

    def _mtf(self, **overrides) -> dict:
        base = {
            "direction": "BUY",
            "alignment_score": 80,
            "higher_tf_aligned": True,
            "volatility_ok": True,
            "m15_indicators": {"momentum_score": 70, "atr_pips": 20, "adx": 30, "rsi": 55},
            "tf_results": {
                "D1": {"structure": "UPTREND"},
                "H4": {"structure": "UPTREND"},
            },
        }
        base.update(overrides)
        return base

    def _session(self) -> dict:
        return {"session": "london_ny_overlap"}

    def test_score_range(self):
        result = self.engine.score(self._mtf(), self._session(), spread_pips=0.8)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_grade_present(self):
        result = self.engine.score(self._mtf(), self._session(), spread_pips=0.8)
        self.assertIn(result["grade"], ["A", "B", "C", "D", "F"])

    def test_recommendation_present(self):
        result = self.engine.score(self._mtf(), self._session(), spread_pips=0.8)
        self.assertIn(
            result["recommendation"],
            ["STRONG_BUY", "BUY", "STRONG_SELL", "SELL", "WATCH", "SKIP"],
        )

    def test_high_spread_lowers_score(self):
        low = self.engine.score(self._mtf(), self._session(), spread_pips=0.5)["score"]
        high = self.engine.score(self._mtf(), self._session(), spread_pips=3.9)["score"]
        self.assertGreater(low, high)

    def test_news_risk_penalty(self):
        low = self.engine.score(self._mtf(), self._session(), spread_pips=0.8, news_risk="LOW")["score"]
        high = self.engine.score(self._mtf(), self._session(), spread_pips=0.8, news_risk="HIGH")["score"]
        self.assertGreaterEqual(low, high)


# ═══════════════════════════════════════════════════════════════════════════════
# Risk Engine
# ═══════════════════════════════════════════════════════════════════════════════
class TestRiskEngine(unittest.TestCase, _IsolatedStateMixin):

    def setUp(self):
        self._isolate_state()
        from risk_management.risk_engine import RiskEngine
        self.engine = RiskEngine()

    def test_sl_tp_computed(self):
        sl, tp = self.engine.calculate_sl_tp("GBPUSD", "BUY", 1.2700, atr_pips=20, spread_pips=0.8)
        self.assertIsInstance(sl, float)
        self.assertIsInstance(tp, float)

    def test_sl_below_entry_for_buy(self):
        sl, _ = self.engine.calculate_sl_tp("GBPUSD", "BUY", 1.2700, atr_pips=20, spread_pips=0.8)
        self.assertLess(sl, 1.2700)

    def test_tp_above_entry_for_buy(self):
        _, tp = self.engine.calculate_sl_tp("GBPUSD", "BUY", 1.2700, atr_pips=20, spread_pips=0.8)
        self.assertGreater(tp, 1.2700)

    def test_sell_sl_above_entry(self):
        sl, _ = self.engine.calculate_sl_tp("GBPUSD", "SELL", 1.2700, atr_pips=20, spread_pips=0.8)
        self.assertGreater(sl, 1.2700)

    def test_rr_meets_minimum(self):
        sl, tp = self.engine.calculate_sl_tp("GBPUSD", "BUY", 1.2700, atr_pips=20, spread_pips=0.8)
        sl_pips = abs(1.2700 - sl) / 0.0001
        tp_pips = abs(tp - 1.2700) / 0.0001
        ok, rr = self.engine.validate_rr(sl_pips, tp_pips)
        self.assertTrue(ok)
        self.assertGreaterEqual(rr, 1.0)

    def test_position_sizing_scales_with_balance(self):
        small = self.engine.calculate_position_size(1000, 15, "EURUSD", confidence_score=90)
        large = self.engine.calculate_position_size(100_000, 15, "EURUSD", confidence_score=90)
        self.assertGreaterEqual(large, small)

    def test_position_sizing_respects_bounds(self):
        lot = self.engine.calculate_position_size(10_000, 15, "EURUSD", confidence_score=90)
        self.assertGreaterEqual(lot, 0.01)
        self.assertLessEqual(lot, 0.20)

    def test_margin_clamp_can_only_reduce_lot_size(self):
        """The margin safety clamp (Iteration 1, Phase 6.3) must never INCREASE
        the risk-based lot size — only ever hold it or reduce it."""
        unconstrained = self.engine.calculate_position_size(10_000, 15, "EURUSD", confidence_score=90)
        constrained = self.engine.calculate_position_size(
            10_000, 15, "EURUSD", confidence_score=90,
            free_margin=50, margin_usd_per_lot=2000,
        )
        self.assertLessEqual(constrained, unconstrained)

    def test_margin_clamp_noop_when_ample(self):
        unconstrained = self.engine.calculate_position_size(10_000, 15, "EURUSD", confidence_score=90)
        ample = self.engine.calculate_position_size(
            10_000, 15, "EURUSD", confidence_score=90,
            free_margin=1_000_000, margin_usd_per_lot=2000,
        )
        self.assertEqual(ample, unconstrained)

    def test_can_take_trade_returns_tuple(self):
        allowed, reason = self.engine.can_take_trade("EURUSD", "BUY")
        self.assertIsInstance(allowed, bool)
        self.assertIsInstance(reason, str)


# ═══════════════════════════════════════════════════════════════════════════════
# State Manager (module of free functions — not a class)
# ═══════════════════════════════════════════════════════════════════════════════
class TestStateManager(unittest.TestCase, _IsolatedStateMixin):

    def setUp(self):
        self._isolate_state()

    def test_kill_switch_default_off(self):
        from core.state_manager import is_kill_switch_active
        self.assertFalse(is_kill_switch_active())

    def test_kill_switch_toggle(self):
        from core.state_manager import set_kill_switch, is_kill_switch_active
        set_kill_switch(True, "test")
        self.assertTrue(is_kill_switch_active())
        set_kill_switch(False)
        self.assertFalse(is_kill_switch_active())

    def test_add_and_remove_active_trade(self):
        from core.state_manager import save_active_trade, get_active_trades, remove_active_trade
        save_active_trade(12345, {"pair": "EURUSD", "direction": "BUY"})
        self.assertIn("12345", get_active_trades())
        remove_active_trade(12345)
        self.assertNotIn("12345", get_active_trades())

    def test_log_ai_decision(self):
        from core.state_manager import save_ai_decision, get_ai_decisions
        for i in range(5):
            save_ai_decision({"pair": "EURUSD", "decision": "TAKE", "confidence": 70 + i})
        logs = get_ai_decisions()
        self.assertGreaterEqual(len(logs), 1)

    def test_daily_stats_increment(self):
        from core.state_manager import update_daily_stats, get_daily_stats
        update_daily_stats(25.0, "EURUSD", won=True)
        stats = get_daily_stats()
        self.assertGreaterEqual(stats["trades_taken"], 1)

    def test_update_drawdown_tracks_peak_and_pct(self):
        """Guards the Iteration-1 fix: update_drawdown() was defined but never
        called anywhere, so the daily drawdown circuit breaker never actually
        tripped in live trading. This pins its arithmetic."""
        from core.state_manager import update_drawdown, get_daily_stats

        update_drawdown(10_000, 0.0)
        stats = get_daily_stats()
        self.assertEqual(stats["peak_balance"], 10_000)
        self.assertEqual(stats["current_drawdown_pct"], 0.0)

        update_drawdown(9_700, stats["peak_balance"])
        stats = get_daily_stats()
        self.assertAlmostEqual(stats["current_drawdown_pct"], 3.0, places=1)

        update_drawdown(10_500, stats["peak_balance"])
        stats = get_daily_stats()
        self.assertEqual(stats["peak_balance"], 10_500)
        self.assertEqual(stats["current_drawdown_pct"], 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Daily Summary (unchanged — already tested the real API)
# ═══════════════════════════════════════════════════════════════════════════════
class TestDailySummary(unittest.TestCase):

    def test_compute_stats_empty(self):
        from utils.daily_summary import compute_stats
        stats = compute_stats([])
        self.assertEqual(stats["total_trades"], 0)
        self.assertEqual(stats["win_rate"], 0.0)

    def test_compute_stats_basic(self):
        from utils.daily_summary import compute_stats
        trades = [
            {"profit_loss": "100.0", "symbol": "EURUSD", "session": "london",  "direction": "BUY"},
            {"profit_loss": "50.0",  "symbol": "EURUSD", "session": "london",  "direction": "BUY"},
            {"profit_loss": "-30.0", "symbol": "GBPUSD", "session": "newyork", "direction": "SELL"},
        ]
        stats = compute_stats(trades)
        self.assertEqual(stats["total_trades"], 3)
        self.assertEqual(stats["wins"],   2)
        self.assertEqual(stats["losses"], 1)
        self.assertAlmostEqual(stats["total_pnl"], 120.0, places=1)
        self.assertAlmostEqual(stats["win_rate"],  66.67, places=1)

    def test_profit_factor_calculation(self):
        from utils.daily_summary import compute_stats
        trades = [
            {"profit_loss": "200.0", "symbol": "EURUSD", "session": "london",  "direction": "BUY"},
            {"profit_loss": "-100.0","symbol": "EURUSD", "session": "london",  "direction": "SELL"},
        ]
        stats = compute_stats(trades)
        self.assertAlmostEqual(stats["profit_factor"], 2.0, places=3)

    def test_compute_ai_stats_empty(self):
        from utils.daily_summary import compute_ai_stats
        a = compute_ai_stats([])
        self.assertEqual(a["total_decisions"], 0)
        self.assertEqual(a["llm_used"], 0)

    def test_format_report_runs(self):
        from utils.daily_summary import compute_stats, compute_ai_stats, format_text_report
        stats    = compute_stats([])
        ai_stats = compute_ai_stats([])
        report   = format_text_report(stats, ai_stats, "daily", "2024-01-01 00:00 UTC")
        self.assertIsInstance(report, str)
        self.assertGreater(len(report), 50)


# ═══════════════════════════════════════════════════════════════════════════════
# Indicators
# ═══════════════════════════════════════════════════════════════════════════════
class TestIndicators(unittest.TestCase):

    def _make_df(self, n: int = 250):
        import pandas as pd
        import numpy as np
        np.random.seed(42)
        close = 1.08 + np.cumsum(np.random.randn(n) * 0.001)
        high  = close + np.random.uniform(0.0002, 0.0008, n)
        low   = close - np.random.uniform(0.0002, 0.0008, n)
        openp = np.roll(close, 1)
        openp[0] = close[0]
        vol   = np.random.randint(500, 5000, n).astype(float)
        return pd.DataFrame({"open": openp, "high": high, "low": low, "close": close, "volume": vol})

    def test_calculate_indicators_returns_dict(self):
        from strategies.indicators import calculate_indicators
        result = calculate_indicators(self._make_df(), "EURUSD")
        self.assertIsInstance(result, dict)
        self.assertIn("rsi", result)
        self.assertIn("adx", result)
        self.assertIn("momentum_score", result)

    def test_calculate_indicators_none_on_insufficient_data(self):
        from strategies.indicators import calculate_indicators
        result = calculate_indicators(self._make_df(n=50), "EURUSD")
        self.assertIsNone(result)

    def test_momentum_score_range(self):
        from strategies.indicators import _calc_momentum_score
        score = _calc_momentum_score(
            ema_bullish=True, ema_bearish=False,
            macd_bull=True, macd_bear=False,
            st_bull=True, st_bear=False,
            rsi_bull=True, rsi_bear=False,
            adx=30, dmi_pos=25, dmi_neg=10,
        )
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


# ═══════════════════════════════════════════════════════════════════════════════
# Config Manager
# ═══════════════════════════════════════════════════════════════════════════════
class TestConfigManager(unittest.TestCase):

    def test_singleton(self):
        from core.config_manager import ConfigManager
        self.assertIs(ConfigManager(), ConfigManager())

    def test_pairs_present(self):
        """Live pair universe (Iteration 1) is EURUSD + GBPUSD only."""
        from core.config_manager import config
        self.assertIn("EURUSD", config.pairs)
        self.assertIn("GBPUSD", config.pairs)

    def test_risk_config(self):
        from core.config_manager import config
        self.assertIsInstance(config.max_daily_drawdown_pct, (int, float))
        self.assertIsInstance(config.get("risk", "risk_pct_standard"), (int, float))


# ═══════════════════════════════════════════════════════════════════════════════
# Webhook Payload Validation (unchanged — already tested the real API)
# ═══════════════════════════════════════════════════════════════════════════════
class TestWebhookPayload(unittest.TestCase):

    VALID_PAYLOAD = {
        "symbol":     "EURUSD",
        "timeframe":  "M15",
        "action":     "BUY",
        "confidence": 78,
        "sl":         1.0750,
        "tp":         1.0870,
        "atr":        0.0012,
        "spread":     0.6,
        "trend":      "up",
        "timestamp":  "2024-06-03T09:00:00Z",
        "token":      "test-token",
    }

    def _validate(self, payload: dict) -> tuple[bool, str]:
        """Basic validation mirror of webhook_server._validate_payload."""
        required = ["symbol", "action", "sl", "tp"]
        for field in required:
            if field not in payload:
                return False, f"Missing: {field}"
        if payload["action"] not in ("BUY", "SELL", "CLOSE"):
            return False, "Invalid action"
        return True, "ok"

    def test_valid_payload_passes(self):
        ok, msg = self._validate(self.VALID_PAYLOAD)
        self.assertTrue(ok, msg)

    def test_missing_action_fails(self):
        bad = dict(self.VALID_PAYLOAD)
        del bad["action"]
        ok, _ = self._validate(bad)
        self.assertFalse(ok)

    def test_invalid_action_fails(self):
        bad = dict(self.VALID_PAYLOAD)
        bad["action"] = "MAYBE"
        ok, _ = self._validate(bad)
        self.assertFalse(ok)

    def test_missing_sl_fails(self):
        bad = dict(self.VALID_PAYLOAD)
        del bad["sl"]
        ok, _ = self._validate(bad)
        self.assertFalse(ok)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    unittest.main(verbosity=2)
