"""
strategies/confidence_engine.py
--------------------------------
Deterministic Win Probability / Confidence Scoring Engine.
Scores 0-100 based on multi-factor analysis.

FULLY DETERMINISTIC — no LLM required.
The LLM may optionally adjust the score UP/DOWN by ±15 points
based on news context and regime interpretation.

Factor weights:
  MTF Alignment       25
  Momentum Quality    20
  Session             15
  Spread              10
  Volatility          10
  ADX Trend Strength  10
  RSI Position         5
  Market Structure     5
  ─────────────────  100
"""

from typing import Dict, Optional

from core.config_manager import config
from core.session_manager import get_session_info, Session
from core.logger import get_logger

logger = get_logger(__name__)


class ConfidenceEngine:
    """
    Scores each trade setup from 0-100.
    Threshold gating is enforced upstream by the decision engine.
    """

    def score(
        self,
        mtf_analysis: Dict,
        session_info: Dict,
        spread_pips: float,
        news_risk: str = "LOW",
        advanced_analysis: Dict = None,
    ) -> Dict:
        """
        Returns:
          score         : float 0-100
          grade         : str A/B/C/D/F
          components    : dict of individual factor scores
          recommendation: str STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL / SKIP
          reason        : str human-readable explanation
        """
        components = {}

        # ---- 1. MTF Alignment (25 pts) ----
        alignment_score = mtf_analysis.get("alignment_score", 0)
        higher_aligned  = mtf_analysis.get("higher_tf_aligned", False)
        mtf_score = min(25.0, (alignment_score / 100) * 25)
        if higher_aligned:
            mtf_score = min(25.0, mtf_score * 1.2)  # Bonus for D1+H4 alignment
        components["mtf_alignment"] = round(mtf_score, 1)

        # ---- 2. Momentum Quality (20 pts) ----
        m15 = mtf_analysis.get("m15_indicators") or {}
        direction = mtf_analysis.get("direction", "NEUTRAL")
        momentum = m15.get("momentum_score", 50)
        if direction == "BUY":
            mom_score = max(0, (momentum - 50) / 50) * 20
        elif direction == "SELL":
            mom_score = max(0, (50 - momentum) / 50) * 20
        else:
            mom_score = 0
        components["momentum"] = round(mom_score, 1)

        # ---- 3. Session Quality (15 pts) ----
        session = session_info.get("session", "off")
        session_scores = {
            Session.OVERLAP.value:   15,
            Session.LONDON.value:    12,
            Session.NEW_YORK.value:  12,
            Session.ASIAN.value:      6,
            Session.OFF.value:        0,
        }
        components["session"] = session_scores.get(session, 5)

        # ---- 4. Spread (10 pts) ----
        max_spread = config.get("risk", "spread_max_pips")
        if spread_pips <= 1.0:
            spread_score = 10
        elif spread_pips <= max_spread:
            spread_score = max(0, 10 - (spread_pips - 1.0) * (10 / (max_spread - 1.0)))
        else:
            spread_score = 0  # Spread too wide — disqualify this factor
        components["spread"] = round(spread_score, 1)

        # ---- 5. Volatility (10 pts) ----
        vol_ok = mtf_analysis.get("volatility_ok", False)
        atr_pips = m15.get("atr_pips", 0)
        min_atr = config.get("indicators", "atr", "volatility_min_pips")
        max_atr = config.get("indicators", "atr", "volatility_max_pips")
        if vol_ok:
            # Ideal ATR zone: 12-40 pips on M15
            if 12 <= atr_pips <= 40:
                vol_score = 10
            elif atr_pips < 12:
                vol_score = (atr_pips / 12) * 10
            else:
                vol_score = max(0, 10 - (atr_pips - 40) / 40 * 10)
        else:
            vol_score = 0
        components["volatility"] = round(vol_score, 1)

        # ---- 6. ADX Trend Strength (10 pts) ----
        adx = m15.get("adx", 0)
        if adx >= config.get("indicators", "adx", "strong_trend"):
            adx_score = 10
        elif adx >= config.get("indicators", "adx", "trending_threshold"):
            adx_score = 7
        elif adx >= 18:
            adx_score = 4
        else:
            adx_score = 0  # Choppy market
        components["adx_strength"] = round(adx_score, 1)

        # ---- 7. RSI Position (5 pts) ----
        rsi = m15.get("rsi", 50)
        if direction == "BUY":
            if 45 <= rsi <= 65:     rsi_score = 5  # Ideal: room to run upward
            elif 40 <= rsi < 45:    rsi_score = 3
            elif rsi > 65:          rsi_score = 1  # Near overbought
            else:                   rsi_score = 0
        elif direction == "SELL":
            if 35 <= rsi <= 55:     rsi_score = 5  # Ideal: room to run downward
            elif 55 < rsi <= 60:    rsi_score = 3
            elif rsi < 35:          rsi_score = 1  # Near oversold
            else:                   rsi_score = 0
        else:
            rsi_score = 2
        components["rsi_position"] = round(rsi_score, 1)

        # ---- 8. Market Structure (5 pts) ----
        structure = {}
        for tf_data in mtf_analysis.get("tf_results", {}).values():
            s = tf_data.get("structure")
            if s:
                structure[s] = structure.get(s, 0) + 1
        dominant_structure = max(structure, key=structure.get) if structure else "UNKNOWN"
        if direction == "BUY" and dominant_structure == "UPTREND":
            struct_score = 5
        elif direction == "SELL" and dominant_structure == "DOWNTREND":
            struct_score = 5
        elif dominant_structure in ("RANGING", "EXPANDING"):
            struct_score = 0
        else:
            struct_score = 2
        components["market_structure"] = round(struct_score, 1)

        # ---- News Risk Penalty ----
        news_penalties = {"LOW": 0, "MEDIUM": -5, "HIGH": -15, "EXTREME": -30}
        news_penalty = news_penalties.get(news_risk.upper(), 0)

        # ---- Advanced Analysis Bonus (0-30 pts) ----
        adv_bonus = 0
        adv_summary = "none"
        if advanced_analysis:
            adv_signal = advanced_analysis.get("signal", "NEUTRAL")
            # Only apply bonus when advanced signal AGREES with direction
            if (adv_signal == "BUY"  and direction == "BUY") or                (adv_signal == "SELL" and direction == "SELL"):
                adv_bonus  = advanced_analysis.get("confidence_bonus", 0)
                adv_summary = " | ".join(advanced_analysis.get("patterns", [])) or "none"
            elif adv_signal != "NEUTRAL" and adv_signal != direction:
                adv_bonus = -8   # penalty when advanced analysis DISAGREES
                adv_summary = f"conflicts ({adv_signal})"
        components["advanced_patterns"] = round(adv_bonus, 1)

        # ---- Total Score ----
        raw_score = sum(components.values())
        final_score = max(0.0, min(100.0, raw_score + news_penalty))

        # ---- Spread Hard Block ----
        spread_blocked = spread_pips > config.get("risk", "spread_max_pips")

        # ---- Grade ----
        grade = self._get_grade(final_score)

        # ---- Recommendation ----
        recommendation, reason = self._get_recommendation(
            final_score, direction, spread_blocked, news_risk, adx
        )

        return {
            "score": round(final_score, 1),
            "grade": grade,
            "components": components,
            "news_penalty": news_penalty,
            "spread_blocked": spread_blocked,
            "dominant_structure": dominant_structure,
            "recommendation": recommendation,
            "reason": reason,
            "direction": direction,
            "advanced_patterns": adv_summary,
            "advanced_bonus": adv_bonus,
        }

    def _get_grade(self, score: float) -> str:
        if score >= 80: return "A"
        if score >= 70: return "B"
        if score >= 60: return "C"
        if score >= 50: return "D"
        return "F"

    def _get_recommendation(
        self, score: float, direction: str, spread_blocked: bool,
        news_risk: str, adx: float
    ) -> tuple:
        if spread_blocked:
            return "SKIP", "Spread too wide — risk/reward compromised"

        if news_risk == "EXTREME":
            return "SKIP", "Extreme news risk — trading paused"

        if direction == "NEUTRAL":
            return "SKIP", "No clear directional bias across timeframes"

        if adx < 18:
            return "SKIP", f"ADX={adx:.0f} — market too choppy, no trend"

        threshold = config.confidence_threshold
        high_threshold = config.get("ai_engine", "high_confidence_threshold")

        if score >= high_threshold:
            return f"STRONG_{direction}", f"High-confidence {direction} — score {score:.0f}/100"
        elif score >= threshold:
            return direction, f"Valid {direction} setup — score {score:.0f}/100"
        elif score >= threshold - 10:
            return "WATCH", f"Marginal setup — score {score:.0f}/100, needs AI confirmation"
        else:
            return "SKIP", f"Low confidence — score {score:.0f}/100 below threshold {threshold}"


# Module-level singleton
confidence_engine = ConfidenceEngine()
