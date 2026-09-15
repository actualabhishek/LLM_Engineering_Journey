"""
strategies/multi_timeframe.py
-----------------------------
Multi-timeframe trend analysis.
Analyzes D1, H4, H1, M15 to assess trend alignment.

DETERMINISTIC logic — no LLM required here.
The AI engine receives MTF output as structured context
and decides whether confluence is sufficient to trade.

Trend hierarchy:
  D1  -> Long-term bias
  H4  -> Medium-term structure
  H1  -> Intermediate trend
  M15 -> Entry-level execution signal
"""

from typing import Dict, Optional, Tuple
import pandas as pd

from strategies.indicators import calculate_indicators, detect_market_structure
from core.logger import get_logger

logger = get_logger(__name__)


class MultiTimeframeAnalysis:
    """
    Given OHLCV data for multiple timeframes, compute:
      1. Individual timeframe trend direction
      2. Alignment score (0-100)
      3. Recommended trade direction
      4. Whether MTF conditions permit a trade
    """

    TIMEFRAME_WEIGHTS = {
        "D1": 0.35,
        "H4": 0.30,
        "H1": 0.20,
        "M15": 0.15,
    }

    def analyze(self, data_by_tf: Dict[str, pd.DataFrame], pair: str) -> Dict:
        """
        data_by_tf: {"M15": df, "H1": df, "H4": df, "D1": df}
        Returns comprehensive MTF analysis dict.
        """
        tf_results = {}
        tf_directions = {}

        for tf, weight in self.TIMEFRAME_WEIGHTS.items():
            df = data_by_tf.get(tf)
            if df is None or len(df) < 50:
                logger.warning(f"{pair} {tf}: insufficient data, skipping")
                continue

            indicators = calculate_indicators(df, pair)
            structure  = detect_market_structure(df)

            if indicators is None:
                continue

            direction = indicators["trend_direction"]
            # Simplify to BUY/SELL/NEUTRAL for alignment scoring
            simple_dir = self._simplify(direction)

            tf_results[tf] = {
                "direction": direction,
                "simple_direction": simple_dir,
                "momentum_score": indicators["momentum_score"],
                "adx": indicators["adx"],
                "rsi": indicators["rsi"],
                "structure": structure["structure"],
                "ema_bullish": indicators["ema_bullish"],
                "ema_bearish": indicators["ema_bearish"],
                "long_trend_bull": indicators["long_trend_bull"],
                "long_trend_bear": indicators["long_trend_bear"],
                "supertrend_bull": indicators["supertrend_bull"],
                "atr_pips": indicators["atr_pips"],
                "volatility_ok": indicators["volatility_ok"],
                "weight": weight,
            }
            tf_directions[tf] = simple_dir

        if not tf_results:
            return {"aligned": False, "direction": "NEUTRAL", "alignment_score": 0, "tf_results": {}}

        # ---- Alignment Scoring ----
        buy_weight  = sum(v["weight"] for v in tf_results.values() if v["simple_direction"] == "BUY")
        sell_weight = sum(v["weight"] for v in tf_results.values() if v["simple_direction"] == "SELL")
        total_weight = sum(v["weight"] for v in tf_results.values())

        if total_weight == 0:
            return {"aligned": False, "direction": "NEUTRAL", "alignment_score": 0, "tf_results": tf_results}

        buy_pct  = (buy_weight  / total_weight) * 100
        sell_pct = (sell_weight / total_weight) * 100

        if buy_pct >= 65:
            consensus_dir = "BUY"
            alignment_score = buy_pct
        elif sell_pct >= 65:
            consensus_dir = "SELL"
            alignment_score = sell_pct
        else:
            consensus_dir = "NEUTRAL"
            alignment_score = max(buy_pct, sell_pct)

        # Check M15 (execution TF) aligns with consensus
        m15_result = tf_results.get("M15", {})
        m15_aligned = m15_result.get("simple_direction") == consensus_dir

        # Volatility gate — require at least M15 and H1 to have valid ATR
        volatility_ok = all(
            tf_results.get(tf, {}).get("volatility_ok", True)
            for tf in ["M15", "H1"]
            if tf in tf_results
        )

        # Strong trend confirmation: D1 + H4 must agree for high-quality setups
        d1_dir  = tf_results.get("D1", {}).get("simple_direction", "NEUTRAL")
        h4_dir  = tf_results.get("H4", {}).get("simple_direction", "NEUTRAL")
        higher_tf_aligned = (d1_dir == h4_dir == consensus_dir)

        # ADX trending confirmation (at least H1 or M15 should be trending)
        h1_adx  = tf_results.get("H1", {}).get("adx", 0)
        m15_adx = tf_results.get("M15", {}).get("adx", 0)
        trending = h1_adx >= 20 or m15_adx >= 20

        # M15 indicators for entry-level detail
        m15_indicators = None
        if "M15" in data_by_tf:
            m15_indicators = calculate_indicators(data_by_tf["M15"], pair)

        is_aligned = (
            consensus_dir != "NEUTRAL"
            and m15_aligned
            and alignment_score >= 65
            and volatility_ok
        )

        return {
            "pair": pair,
            "aligned": is_aligned,
            "direction": consensus_dir,
            "alignment_score": round(alignment_score, 1),
            "higher_tf_aligned": higher_tf_aligned,
            "m15_aligned": m15_aligned,
            "trending": trending,
            "volatility_ok": volatility_ok,
            "tf_results": tf_results,
            "m15_indicators": m15_indicators,
            "buy_weight_pct": round(buy_pct, 1),
            "sell_weight_pct": round(sell_pct, 1),
            # Human-readable summary for AI context
            "summary": self._build_summary(
                pair, consensus_dir, alignment_score, tf_results, higher_tf_aligned
            ),
        }

    def _simplify(self, direction: str) -> str:
        if direction in ("BUY", "BUY_WEAK"):
            return "BUY"
        if direction in ("SELL", "SELL_WEAK"):
            return "SELL"
        return "NEUTRAL"

    def _build_summary(
        self,
        pair: str,
        direction: str,
        score: float,
        tf_results: Dict,
        higher_aligned: bool
    ) -> str:
        """Compact human-readable summary for LLM context injection."""
        lines = [f"{pair} MTF Analysis — Consensus: {direction} (Alignment: {score:.0f}%)"]
        for tf, res in tf_results.items():
            lines.append(
                f"  {tf}: {res['simple_direction']} | ADX={res.get('adx',0):.0f} "
                f"| RSI={res.get('rsi',50):.0f} | Structure={res.get('structure','?')}"
            )
        lines.append(f"  Higher TF Aligned (D1+H4): {higher_aligned}")
        return "\n".join(lines)


# Module-level singleton
mtf_analyzer = MultiTimeframeAnalysis()
