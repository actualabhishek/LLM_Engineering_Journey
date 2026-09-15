"""
news_engine/news_sentiment.py
------------------------------
Live news sentiment engine for forex trading decisions.
Uses Finnhub news API (free tier) to fetch real-time forex news
and scores sentiment per currency pair.

How it works:
  1. Fetches latest forex news from Finnhub every 15 minutes
  2. Matches headlines to relevant currency pairs
  3. Scores sentiment using keyword analysis + Claude AI
  4. Returns sentiment summary to decision engine before each trade

Usage:
  from news_engine.news_sentiment import news_sentiment
  ctx = news_sentiment.get_sentiment("GBPJPY")
  # Returns: {"sentiment": "BEARISH", "score": -2, "headlines": [...], "summary": "..."}
"""

import os
import re
import time
import threading
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from core.config_manager import config
from core.logger import get_logger

logger = get_logger("news_sentiment")

# ── Currency keyword mapping ─────────────────────────────────────────────────
CURRENCY_KEYWORDS = {
    "USD": [
        "dollar", "USD", "fed", "federal reserve", "powell", "fomc",
        "us economy", "us gdp", "us cpi", "us jobs", "nonfarm", "NFP",
        "US inflation", "US rate", "treasury", "US debt"
    ],
    "GBP": [
        "pound", "GBP", "sterling", "bank of england", "BOE", "bailey",
        "UK economy", "UK gdp", "UK cpi", "UK inflation", "UK rate",
        "UK jobs", "brexit", "UK budget"
    ],
    "EUR": [
        "euro", "EUR", "ECB", "european central bank", "lagarde",
        "EU economy", "eurozone", "EU gdp", "EU cpi", "EU inflation",
        "germany", "france", "EU rate"
    ],
    "JPY": [
        "yen", "JPY", "bank of japan", "BOJ", "ueda", "kuroda",
        "japan economy", "japan gdp", "japan cpi", "japan inflation",
        "BOJ intervention", "japan rate", "japan yield"
    ],
    "AUD": [
        "aussie", "AUD", "RBA", "reserve bank australia", "australia",
        "AU economy", "AU gdp", "AU cpi", "iron ore", "china demand"
    ],
    "CAD": [
        "loonie", "CAD", "BOC", "bank of canada", "canada",
        "CA economy", "CA gdp", "oil price", "crude", "WTI", "OPEC"
    ],
}

# ── Bullish/Bearish keywords per currency direction ──────────────────────────
BULLISH_KEYWORDS = [
    "rate hike", "hawkish", "strong", "beats expectations", "better than expected",
    "surplus", "growth", "recovery", "rally", "surge", "positive", "upbeat",
    "resilient", "robust", "tightening", "intervention buy", "raise rates",
    "higher rates", "hot inflation", "strong jobs", "beats forecast"
]

BEARISH_KEYWORDS = [
    "rate cut", "dovish", "weak", "misses expectations", "worse than expected",
    "deficit", "recession", "decline", "slowdown", "drop", "negative", "concern",
    "uncertainty", "easing", "intervention sell", "cut rates", "lower rates",
    "cool inflation", "job losses", "misses forecast", "contraction"
]

# ── Pair to currencies mapping ───────────────────────────────────────────────
PAIR_CURRENCIES = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "GBPJPY": ("GBP", "JPY"),
    "EURJPY": ("EUR", "JPY"),
    "AUDUSD": ("AUD", "USD"),
    "USDCAD": ("USD", "CAD"),
    "USDJPY": ("USD", "JPY"),
    "AUDJPY": ("AUD", "JPY"),
    "EURGBP": ("EUR", "GBP"),
}

# Cache TTL
_NEWS_CACHE_TTL = 900  # 15 minutes


class NewsSentimentEngine:

    def __init__(self):
        self._news_cache: List[Dict] = []
        self._last_fetch: float = 0
        self._lock = threading.Lock()
        self._finnhub_key = (
            config.get("news", "finnhub_api_key")
            or os.getenv("FINNHUB_API_KEY")
            or ""
        )
        # Fetch initial news
        self._fetch_news()

    def _fetch_news(self) -> None:
        """Fetch latest forex news from Finnhub."""
        if not self._finnhub_key:
            logger.debug("No Finnhub key — news sentiment disabled")
            return

        try:
            url = f"https://finnhub.io/api/v1/news?category=forex&token={self._finnhub_key}"
            resp = requests.get(url, timeout=10)

            if resp.status_code == 200:
                articles = resp.json()
                # Filter to last 4 hours only
                cutoff = time.time() - 4 * 3600
                recent = [a for a in articles if a.get("datetime", 0) > cutoff]

                with self._lock:
                    self._news_cache = recent
                    self._last_fetch = time.time()

                logger.info(f"News sentiment: {len(recent)} articles fetched (last 4h)")
            else:
                logger.debug(f"Finnhub news returned {resp.status_code}")
        except Exception as e:
            logger.debug(f"News fetch failed: {e}")

    def _refresh_if_needed(self) -> None:
        """Refresh news cache if older than TTL."""
        if time.time() - self._last_fetch > _NEWS_CACHE_TTL:
            thread = threading.Thread(target=self._fetch_news, daemon=True)
            thread.start()

    def _score_article(self, article: Dict, currency: str) -> Tuple[int, str]:
        """
        Score a single article for a currency.
        Returns (score, direction) where score is -3 to +3
        and direction is BULLISH, BEARISH, or NEUTRAL.
        """
        text = (
            (article.get("headline", "") + " " + article.get("summary", "")).lower()
        )

        # Check if article is relevant to this currency
        keywords = CURRENCY_KEYWORDS.get(currency, [])
        relevant = any(kw.lower() in text for kw in keywords)
        if not relevant:
            return 0, "NEUTRAL"

        # Score bullish/bearish signals
        bull_score = sum(1 for kw in BULLISH_KEYWORDS if kw.lower() in text)
        bear_score = sum(1 for kw in BEARISH_KEYWORDS if kw.lower() in text)

        net = bull_score - bear_score

        if net >= 2:
            return 3, "BULLISH"
        elif net == 1:
            return 1, "BULLISH"
        elif net == -1:
            return -1, "BEARISH"
        elif net <= -2:
            return -3, "BEARISH"
        else:
            return 0, "NEUTRAL"

    def get_sentiment(self, pair: str) -> Dict:
        """
        Get news sentiment for a currency pair.

        Returns:
        {
            "sentiment":       "BULLISH" | "BEARISH" | "NEUTRAL",
            "score":           -3 to +3 (base currency relative to quote),
            "base_sentiment":  sentiment for base currency,
            "quote_sentiment": sentiment for quote currency,
            "headlines":       list of relevant headlines (max 3),
            "summary":         short text for Claude prompt,
            "article_count":   number of relevant articles found,
        }
        """
        self._refresh_if_needed()

        currencies = PAIR_CURRENCIES.get(pair.upper(), ())
        if not currencies:
            # Parse from pair name
            if len(pair) == 6:
                currencies = (pair[:3].upper(), pair[3:].upper())
            else:
                return self._neutral_result()

        base_ccy, quote_ccy = currencies

        with self._lock:
            articles = list(self._news_cache)

        if not articles:
            return self._neutral_result()

        # Score each article for base and quote currency
        base_scores  = []
        quote_scores = []
        headlines    = []

        for article in articles:
            b_score, b_dir = self._score_article(article, base_ccy)
            q_score, q_dir = self._score_article(article, quote_ccy)

            if b_score != 0 or q_score != 0:
                headlines.append({
                    "text":      article.get("headline", "")[:100],
                    "source":    article.get("source", ""),
                    "time":      datetime.fromtimestamp(
                                    article.get("datetime", 0), tz=timezone.utc
                                 ).strftime("%H:%M UTC"),
                    "base_dir":  b_dir,
                    "quote_dir": q_dir,
                })

            if b_score != 0:
                base_scores.append(b_score)
            if q_score != 0:
                quote_scores.append(q_score)

        # Aggregate scores
        base_net  = sum(base_scores)  / max(len(base_scores), 1)  if base_scores  else 0
        quote_net = sum(quote_scores) / max(len(quote_scores), 1) if quote_scores else 0

        # Pair sentiment: positive = bullish on pair (base up, quote down)
        pair_score = base_net - quote_net

        # Determine overall direction
        if pair_score >= 1.5:
            sentiment = "BULLISH"
        elif pair_score <= -1.5:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"

        # Build summary for Claude prompt
        top_headlines = headlines[:3]
        if top_headlines:
            hl_text = " | ".join(
                f"[{h['time']}] {h['text']}" for h in top_headlines
            )
            summary = (
                f"{base_ccy} news: {self._dir_from_score(base_net)} "
                f"| {quote_ccy} news: {self._dir_from_score(quote_net)} "
                f"| Recent: {hl_text}"
            )
        else:
            summary = f"No significant {base_ccy}/{quote_ccy} news in last 4 hours"

        return {
            "sentiment":       sentiment,
            "score":           round(pair_score, 2),
            "base_sentiment":  self._dir_from_score(base_net),
            "quote_sentiment": self._dir_from_score(quote_net),
            "headlines":       top_headlines,
            "summary":         summary,
            "article_count":   len(base_scores) + len(quote_scores),
        }

    def _dir_from_score(self, score: float) -> str:
        if score >= 0.5:
            return "BULLISH"
        elif score <= -0.5:
            return "BEARISH"
        return "NEUTRAL"

    def _neutral_result(self) -> Dict:
        return {
            "sentiment":       "NEUTRAL",
            "score":           0,
            "base_sentiment":  "NEUTRAL",
            "quote_sentiment": "NEUTRAL",
            "headlines":       [],
            "summary":         "No news data available",
            "article_count":   0,
        }

    def format_for_prompt(self, pair: str) -> str:
        """
        Format news sentiment as a string for the Claude decision prompt.
        """
        ctx = self.get_sentiment(pair)
        lines = [
            f"LIVE NEWS SENTIMENT ({pair}):",
            f"  Overall: {ctx['sentiment']} (score: {ctx['score']:+.1f})",
            f"  Base currency news:  {ctx['base_sentiment']}",
            f"  Quote currency news: {ctx['quote_sentiment']}",
            f"  Articles analysed:   {ctx['article_count']}",
        ]
        if ctx["headlines"]:
            lines.append("  Recent headlines:")
            for h in ctx["headlines"][:3]:
                lines.append(f"    [{h['time']}] {h['text']}")
        else:
            lines.append("  No relevant headlines in last 4 hours")
        return "\n".join(lines)


# Singleton
news_sentiment = NewsSentimentEngine()
