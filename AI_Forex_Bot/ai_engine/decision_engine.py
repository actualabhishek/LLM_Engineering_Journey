"""
ai_engine/decision_engine.py
-----------------------------
Hybrid AI Decision Engine.

Philosophy:
  1. Run full deterministic analysis first (fast, free, no hallucination risk)
  2. Use LLM ONLY when:
     - Score is in marginal zone (55-75)
     - News context needs interpretation
     - Regime is ambiguous or changing
     - Multi-currency correlation needs assessment
  3. Cache LLM decisions for 15 minutes per pair
  4. If LLM fails → fall back to deterministic score
  5. LLM can adjust score by at most ±15 points (bounded)

LLM Decision Prompt is concise, structured, returns JSON.
This prevents hallucination and forces constrained output.

When AI is NOT used:
  - Score > 80 (trade confidently — deterministic is sufficient)
  - Score < 50 (skip confidently — no LLM will save this)
  - No news events in window
  - Market is trending cleanly with full alignment
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import os
try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

try:
    import openai as _openai
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

from core.config_manager import config
from core.logger import get_logger
try:
    from core.logger import AIDecisionLogger
except ImportError:
    class AIDecisionLogger:
        @staticmethod
        def log(**kwargs): pass

try:
    from news_engine.news_sentiment import news_sentiment as _news_sentiment
    _SENTIMENT_AVAILABLE = True
except Exception:
    _SENTIMENT_AVAILABLE = False
from core.state_manager import save_ai_decision
from strategies.confidence_engine import confidence_engine

logger = get_logger(__name__)

# In-memory LLM decision cache: {pair: {"result": dict, "expires": float}}
_llm_cache: Dict[str, Dict] = {}
_CACHE_TTL_SECONDS = config.get("ai_engine", "llm_cache_minutes", default=15) * 60


def _get_sentiment_block(pair: str) -> str:
    """Get live news sentiment string for Claude prompt."""
    try:
        if _SENTIMENT_AVAILABLE:
            return _news_sentiment.format_for_prompt(pair)
    except Exception:
        pass
    return "LIVE NEWS SENTIMENT: Unavailable"


class DecisionEngine:
    """
    Master decision engine.
    Orchestrates: deterministic scoring → optional LLM → final decision.
    """

    def __init__(self):
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        """
        Initialize AI client — supports both Anthropic API and local Ollama.
        Set ai_engine.provider in config.json:
          "anthropic" → uses ANTHROPIC_API_KEY (default)
          "ollama"    → uses local Ollama server (free, no API key needed)
        """
        provider = config.get("ai_engine", "provider") or "anthropic"

        if provider == "ollama":
            ollama_url  = config.get("ai_engine", "ollama_url") or "http://localhost:11434"
            ollama_model= config.get("ai_engine", "ollama_model") or "llama3.2"
            try:
                import requests
                resp = requests.get(f"{ollama_url}/api/tags", timeout=3)
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    if any(ollama_model in m for m in models):
                        self._client = {"type": "ollama", "url": ollama_url, "model": ollama_model}
                        logger.info(f"Ollama client initialized — model: {ollama_model} @ {ollama_url}")
                    else:
                        logger.warning(f"Ollama model '{ollama_model}' not found. Available: {models}")
                        logger.warning("Run: ollama pull llama3.2 — falling back to deterministic")
                        self._client = None
            except Exception as e:
                logger.warning(f"Ollama not reachable at {ollama_url}: {e} — falling back to deterministic")
                self._client = None

        elif provider == "openai":
            try:
                api_key = (config.get("ai_engine", "openai_api_key")
                           or os.getenv("OPENAI_API_KEY"))
                # Try openai_model first, then fall back to "model" key
                model = (config.get("ai_engine", "openai_model")
                         or config.get("ai_engine", "model")
                         or "gpt-5.4-mini")
                if not _OPENAI_AVAILABLE:
                    logger.warning("openai package not installed — run: pip install openai")
                    self._client = None
                    return
                if not api_key:
                    logger.warning("OPENAI_API_KEY not set in .env or config")
                    self._client = None
                    return
                if api_key and _OPENAI_AVAILABLE:
                    client = _openai.OpenAI(api_key=api_key)
                    self._client = {"type": "openai", "client": client, "model": model}
                    logger.info(f"OpenAI client initialized — model: {model}")
                else:
                    logger.warning("OpenAI API key not set or openai package not installed")
                    self._client = None
            except Exception as e:
                logger.warning(f"OpenAI init failed: {e} — falling back to deterministic")
                self._client = None

        else:  # anthropic claude (default)
            try:
                api_key = (config.get("ai_engine", "anthropic_api_key")
                           or os.getenv("ANTHROPIC_API_KEY"))
                model = (config.get("ai_engine", "anthropic_model")
                         or "claude-sonnet-4-20250514")
                if not api_key:
                    logger.warning("ANTHROPIC_API_KEY not set — deterministic mode")
                    self._client = None
                elif not _ANTHROPIC_AVAILABLE:
                    logger.warning("anthropic package not installed")
                    self._client = None
                elif config.ai_enabled:
                    self._client = {
                        "type":   "anthropic",
                        "client": anthropic.Anthropic(api_key=api_key),
                        "model":  model,
                    }
                    logger.info(f"Claude client ready — model: {model}")
                else:
                    self._client = None
            except Exception as e:
                logger.warning(f"Claude init failed: {e}")
                self._client = None

    def evaluate(
        self,
        pair: str,
        signal_direction: str,
        mtf_analysis: Dict,
        session_info: Dict,
        spread_pips: float,
        news_context: Dict,
        advanced_analysis: Dict = None,
        signal_confidence: float = 0.0,
    ) -> Dict:
        """
        Full evaluation pipeline.
        Returns final trade decision dict.
        """
        # Step 1: Deterministic confidence score
        news_risk = news_context.get("risk_level", "LOW")
        det_result = confidence_engine.score(
            mtf_analysis=mtf_analysis,
            session_info=session_info,
            spread_pips=spread_pips,
            news_risk=news_risk,
            advanced_analysis=advanced_analysis,
        )

        # Use signal engine direction if confidence engine returned NEUTRAL
        ce_direction = det_result.get("direction", "NEUTRAL")
        direction = signal_direction if ce_direction == "NEUTRAL" else ce_direction
        if direction != ce_direction:
            det_result["direction"] = direction
        det_score = det_result["score"]

        # Blend signal engine confidence with indicator score
        # Weights adapt to signal confidence level:
        #   High signal (>85): 70% signal / 30% indicators (leading signals dominate)
        #   Medium signal (65-85): 60% signal / 40% indicators
        #   Low signal (<65): 50% / 50% (equal weight, both must agree)
        if signal_confidence > 0 and direction != "NEUTRAL":
            if signal_confidence >= 85:
                sw, iw = 0.70, 0.30
            elif signal_confidence >= 65:
                sw, iw = 0.60, 0.40
            else:
                sw, iw = 0.50, 0.50
            blended = (det_score * iw) + (signal_confidence * sw)
            if blended > det_score:
                logger.debug(f"Score blended: indicator={det_score:.0f}×{iw} + signal={signal_confidence:.0f}×{sw} → {blended:.0f}")
                det_score = round(blended, 1)
                det_result["score"] = det_score

        recommendation = det_result["recommendation"]
        llm_used = False
        llm_adjustment = 0
        llm_reasoning = ""

        # Step 2: Decide whether LLM is needed
        # Use blended score (already accounts for signal engine confidence)
        # If blended score >= 80, skip LLM — clear signal
        needs_llm = self._should_use_llm(
            det_score=det_score,  # already blended at this point
            news_context=news_context,
            mtf_analysis=mtf_analysis,
            recommendation=recommendation,
        )

        final_score = det_score

        if needs_llm and self._client:
            llm_result = self._query_llm(
                pair=pair,
                direction=direction,
                det_score=det_score,
                mtf_summary=mtf_analysis.get("summary", ""),
                news_context=news_context,
                session_info=session_info,
                indicators=mtf_analysis.get("m15_indicators") or {},
                advanced_summary=advanced_analysis.get("summary", "") if advanced_analysis else "",
                signal_confidence=signal_confidence,
            )
            if llm_result:
                llm_used = True
                # Bound LLM adjustment to ±15 points
                raw_adj = llm_result.get("score_adjustment", 0)
                llm_adjustment = max(-15, min(15, raw_adj))
                llm_reasoning = llm_result.get("reasoning", "")
                final_score = max(0, min(100, det_score + llm_adjustment))
                logger.info(
                    f"[LLM] {pair} {direction} | Base={det_score:.0f} "
                    f"adj={llm_adjustment:+.0f} → final={final_score:.0f} | "
                    f"{llm_reasoning[:80]}"
                )

        # Step 3: Apply final session threshold
        # Note: we do NOT gate on recommendation=="SKIP" here because the
        # recommendation is recalculated from the pre-LLM score; we use the
        # final_score (post LLM + advanced bonus) as the single source of truth.
        min_confidence = session_info.get("min_confidence_required", 65)
        hard_blocked = (
            direction == "NEUTRAL"
            or det_result.get("spread_blocked", False)
            or news_risk in ("HIGH", "EXTREME")
        )
        trade_allowed = final_score >= min_confidence and not hard_blocked

        final_rec = "TAKE" if trade_allowed else "SKIP"
        if trade_allowed and final_score >= config.get("ai_engine", "high_confidence_threshold"):
            final_rec = "STRONG_TAKE"

        result = {
            "pair": pair,
            "direction": direction,
            "decision": final_rec,
            "final_score": round(final_score, 1),
            "deterministic_score": round(det_score, 1),
            "llm_used": llm_used,
            "llm_adjustment": llm_adjustment,
            "llm_reasoning": llm_reasoning,
            "grade": det_result["grade"],
            "components": det_result["components"],
            "recommendation": recommendation,
            "news_risk": news_risk,
            "session": session_info.get("session"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sl_pips": mtf_analysis.get("m15_indicators", {}).get("sl_distance_pips", 20),
            "tp_pips": mtf_analysis.get("m15_indicators", {}).get("tp_distance_pips", 40),
        }

        # Step 4: Log decision
        AIDecisionLogger.log(
            pair=pair,
            signal_type=direction,
            confidence=final_score,
            reasoning=llm_reasoning or det_result["reason"],
            indicators=mtf_analysis.get("m15_indicators") or {},
            llm_used=llm_used,
            decision=final_rec,
        )
        save_ai_decision({
            "pair": pair,
            "direction": direction,
            "score": final_score,
            "decision": final_rec,
            "llm_used": llm_used,
        })

        logger.info(
            f"[DECISION] {pair} {direction} | Score={final_score:.0f} "
            f"| {'LLM+' if llm_used else 'DET'} | → {final_rec}"
        )

        return result

    def _should_use_llm(
        self,
        det_score: float,
        news_context: Dict,
        mtf_analysis: Dict,
        recommendation: str,
    ) -> bool:
        """
        Determine if LLM reasoning adds value.

        LLM IS used when:
          - Score in marginal zone 55-75 (uncertain)
          - News risk is MEDIUM or higher
          - MTF alignment < 80% (not a clean trend)
          - Regime detection needed (structure changing)

        LLM NOT used when:
          - Score >= 80 (clear high-confidence setup)
          - Score < 50 (clear skip)
          - No news events
          - Clean trend alignment >= 85%
          - LLM disabled in config
        """
        if not config.ai_enabled:
            return False

        use_llm_for = config.get("ai_engine", "use_llm_for") or []

        # Deterministic decisions that don't need LLM
        if det_score >= 80:
            return False  # Clear signal — no ambiguity
        if det_score < 50:
            return False  # Clear skip — LLM won't help

        # LLM valuable in marginal zone
        if 55 <= det_score <= 75:
            return True

        # News interpretation
        if news_context.get("risk_level") in ("MEDIUM", "HIGH") and "news_interpretation" in use_llm_for:
            return True

        # Regime detection when alignment is borderline
        alignment = mtf_analysis.get("alignment_score", 0)
        if alignment < 75 and "regime_detection" in use_llm_for:
            return True

        return False

    def _query_llm(
        self,
        pair: str,
        direction: str,
        det_score: float,
        mtf_summary: str,
        news_context: Dict,
        session_info: Dict,
        indicators: Dict,
        advanced_summary: str = "",
        signal_confidence: float = 0.0,
    ) -> Optional[Dict]:
        """
        Query LLM for trade decision adjustment.
        Checks cache first. Returns structured JSON result.
        """
        cache_key = f"{pair}_{direction}"
        cached = _llm_cache.get(cache_key)
        if cached and time.time() < cached.get("expires", 0):
            logger.debug(f"LLM cache hit for {pair}")
            return cached["result"]

        prompt = self._build_prompt(
            pair, direction, det_score, mtf_summary,
            news_context, session_info, indicators,
            advanced_summary=advanced_summary,
            signal_confidence=signal_confidence,
        )

        try:
            # Route to correct provider
            if isinstance(self._client, dict) and self._client.get("type") == "openai":
                # Try max_completion_tokens (newer models) then fall back to max_tokens
                oai_kwargs = {
                    "model": self._client["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": config.get("ai_engine", "temperature") or 0.1,
                }
                try:
                    oai_resp = self._client["client"].chat.completions.create(
                        **oai_kwargs, max_completion_tokens=400
                    )
                except TypeError:
                    oai_resp = self._client["client"].chat.completions.create(
                        **oai_kwargs, max_tokens=400
                    )
                text = oai_resp.choices[0].message.content.strip()
            elif isinstance(self._client, dict) and self._client.get("type") == "ollama":
                import requests as _req
                ollama_resp = _req.post(
                    f"{self._client['url']}/api/generate",
                    json={
                        "model":  self._client["model"],
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": config.get("ai_engine", "temperature") or 0.1,
                            "num_predict": 400,
                        }
                    },
                    timeout=30,
                )
                text = ollama_resp.json().get("response", "").strip()
            elif isinstance(self._client, dict) and self._client.get("type") == "anthropic":
                response = self._client["client"].messages.create(
                    model=self._client["model"],
                    max_tokens=400,
                    system="You are a forex trade analyst. Respond ONLY with a valid JSON object. No preamble, no markdown. Start with { and end with }.",
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.content[0].text.strip()
            else:
                # Legacy direct anthropic object
                response = self._client.messages.create(
                    model=config.get("ai_engine", "anthropic_model") or "claude-sonnet-4-20250514",
                    max_tokens=400,
                    system="You are a forex trade analyst. Respond ONLY with a valid JSON object. No preamble, no markdown. Start with { and end with }.",
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.content[0].text.strip()

            # Robust JSON extraction
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            if not text.startswith("{"):
                start = text.find("{")
                end   = text.rfind("}") + 1
                if start >= 0 and end > start:
                    text = text[start:end]

            result = json.loads(text)

            # Validate expected keys
            if "score_adjustment" not in result or "reasoning" not in result:
                raise ValueError("Missing required keys in LLM response")

            # Cache result
            _llm_cache[cache_key] = {
                "result": result,
                "expires": time.time() + _CACHE_TTL_SECONDS
            }
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"LLM JSON parse error for {pair}: {e}")
            return None
        except Exception as e:
            logger.warning(f"LLM query failed for {pair}: {e} — falling back to deterministic")
            return None

    def _build_prompt(
        self,
        pair: str,
        direction: str,
        det_score: float,
        mtf_summary: str,
        news_context: Dict,
        session_info: Dict,
        indicators: Dict,
        advanced_summary: str = "",
        signal_confidence: float = 0.0,
    ) -> str:
        """
        Concise structured prompt.
        Forces JSON output to prevent hallucination.
        Temperature=0.1 keeps reasoning consistent.
        """
        news_events = news_context.get("events", [])
        news_str = json.dumps(news_events[:3]) if news_events else "None"

        return f"""You are a senior institutional forex analyst reviewing a potential {direction} trade on {pair}.

DETERMINISTIC ANALYSIS SCORE: {det_score:.0f}/100
REQUIRED MINIMUM: {config.confidence_threshold}

MULTI-TIMEFRAME SUMMARY:
{mtf_summary}

KEY INDICATORS (M15):
- RSI: {indicators.get('rsi', 'N/A')}
- ADX: {indicators.get('adx', 'N/A')}
- ATR (pips): {indicators.get('atr_pips', 'N/A')}
- Momentum Score: {indicators.get('momentum_score', 'N/A')}
- Supertrend: {'Bullish' if indicators.get('supertrend_bull') else 'Bearish' if indicators.get('supertrend_bear') else 'N/A'}

SESSION: {session_info.get('session', 'unknown')} (Aggressive: {session_info.get('is_aggressive', False)})

NEWS EVENTS IN NEXT 60 MIN: {news_str}
NEWS RISK LEVEL: {news_context.get('risk_level', 'LOW')}
{_get_sentiment_block(pair)}
SIGNAL ENGINE: Confidence={signal_confidence:.0f} (leading indicators: EMA trigger, HTF bias, volume, structure)
NOTE: The deterministic score reflects lagging indicators. Signal engine uses leading indicators and fires earlier.
      A high signal engine confidence with aligned HTF bias is a valid early entry — weigh accordingly.
ADVANCED PATTERNS: {advanced_summary if advanced_summary else 'None detected'}

TASK: Assess whether this trade setup has genuine edge.
Consider: trend quality, momentum sustainability, news risk, session quality.

If live news CONFIRMS signal direction → +5 to +8 adjustment.
If live news OPPOSES signal direction → -5 to -10 adjustment.

YOUR RESPONSE MUST BE ONLY THIS JSON OBJECT (no text before or after):
{{
  "score_adjustment": <integer between -15 and +15>,
  "reasoning": "<1-2 sentences explaining your adjustment>",
  "key_risk": "<single biggest risk factor>",
  "trade_quality": "<HIGH|MEDIUM|LOW>"
}}"""


# Module-level singleton
decision_engine = DecisionEngine()
