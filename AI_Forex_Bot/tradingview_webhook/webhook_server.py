"""
tradingview_webhook/webhook_server.py
--------------------------------------
FastAPI webhook receiver for TradingView alerts.

Security:
  - HMAC token validation
  - Signal age check (max 60 seconds old)
  - Duplicate signal prevention (dedup cache)
  - Rate limiting (max 10 signals/minute per pair)

Signal flow:
  TradingView Alert → Webhook → Signal validation
  → AI Decision Engine → Risk Check → MT5 Execution

Run with: uvicorn tradingview_webhook.webhook_server:app --host 0.0.0.0 --port 8000
"""

import hashlib
import hmac
import json
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator

from core.config_manager import config
from core.logger import get_logger
from core.state_manager import is_kill_switch_active, set_kill_switch
from trading_orchestrator import TradingOrchestrator

logger = get_logger(__name__)
app = FastAPI(title="ForexAI Trader Webhook", version="1.0.0")
orchestrator = TradingOrchestrator()

# Dedup cache: {signal_hash: timestamp}
_dedup_cache: Dict[str, float] = {}
_DEDUP_TTL = 300  # 5 minutes

# Rate limiter: {pair: deque of timestamps}
_rate_limiter: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST"],
    allow_headers=["*"],
)


# ============================================================
# Signal Schema
# ============================================================

class TradingViewSignal(BaseModel):
    """
    Expected webhook payload from TradingView Pine Script.
    All fields required for production trading.
    """
    symbol: str                    # "EURUSD"
    timeframe: str                 # "15"
    signal: str                    # "BUY" | "SELL" | "CLOSE" | "CLOSE_BUY" | "CLOSE_SELL"
    confidence: Optional[float] = None  # 0-100 (from Pine Script scoring)
    trend: Optional[str] = None    # "UPTREND" | "DOWNTREND" | "NEUTRAL"
    sl: Optional[float] = None     # Stop loss price
    tp: Optional[float] = None     # Take profit price
    atr: Optional[float] = None    # Current ATR value
    rsi: Optional[float] = None    # Current RSI
    adx: Optional[float] = None    # Current ADX
    macd_hist: Optional[float] = None  # MACD histogram value
    timestamp: Optional[str] = None   # ISO format UTC timestamp

    @validator("symbol")
    def validate_symbol(cls, v):
        allowed = config.pairs
        if v not in allowed:
            raise ValueError(f"Symbol {v} not in allowed pairs: {allowed}")
        return v

    @validator("signal")
    def validate_signal(cls, v):
        allowed = {"BUY", "SELL", "CLOSE", "CLOSE_BUY", "CLOSE_SELL", "SCALE_IN"}
        if v.upper() not in allowed:
            raise ValueError(f"Signal '{v}' not allowed")
        return v.upper()


# ============================================================
# Middleware & Security
# ============================================================

def _validate_token(token: Optional[str]) -> bool:
    """HMAC-style token validation."""
    expected = config.webhook_secret
    if not expected or expected == "CHANGE_THIS_SECRET_TOKEN":
        logger.warning("Webhook secret not configured — accepting all requests (INSECURE)")
        return True
    if not token:
        return False
    return hmac.compare_digest(token, expected)


def _is_duplicate(signal_hash: str) -> bool:
    """Check if this exact signal was received recently."""
    now = time.time()
    # Cleanup old entries
    expired = [k for k, v in _dedup_cache.items() if now - v > _DEDUP_TTL]
    for k in expired:
        del _dedup_cache[k]

    if signal_hash in _dedup_cache:
        return True
    _dedup_cache[signal_hash] = now
    return False


def _is_rate_limited(pair: str) -> bool:
    """Rate limit: max 10 signals per pair per minute."""
    now = time.time()
    timestamps = _rate_limiter[pair]
    # Remove old timestamps
    while timestamps and now - timestamps[0] > _RATE_LIMIT_WINDOW:
        timestamps.popleft()
    if len(timestamps) >= _RATE_LIMIT_MAX:
        return True
    timestamps.append(now)
    return False


def _is_signal_stale(timestamp_str: Optional[str]) -> bool:
    """Reject signals older than max_signal_age_seconds."""
    if not timestamp_str:
        return False
    try:
        signal_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - signal_time).total_seconds()
        max_age = config.get("webhook", "max_signal_age_seconds", default=60)
        return age > max_age
    except Exception:
        return False


# ============================================================
# Endpoints
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "ok",
        "kill_switch": is_kill_switch_active(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }


@app.post("/webhook")
async def receive_signal(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Main webhook endpoint.
    Validates, deduplicates, and processes TradingView signals.
    Returns immediately; processing happens in background.
    """
    # Parse body first so we can read token from JSON payload
    try:
        body = await request.body()
        data = json.loads(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    # Token validation — check header, query param, OR JSON body (TradingView sends in body)
    token = (
        request.headers.get("X-TV-Token")
        or request.query_params.get("token")
        or data.get("token")          # ← TradingView puts it here in the message JSON
    )
    if not _validate_token(token):
        logger.warning(f"Invalid webhook token from {request.client.host}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    # Validate signal schema
    try:
        signal = TradingViewSignal(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Kill switch check
    if is_kill_switch_active() and signal.signal not in ("CLOSE", "CLOSE_BUY", "CLOSE_SELL"):
        return {"status": "skipped", "reason": "Kill switch active"}

    # Stale signal check
    if _is_signal_stale(signal.timestamp):
        logger.warning(f"Stale signal rejected: {signal.symbol} {signal.signal}")
        return {"status": "skipped", "reason": "Signal too old"}

    # Rate limiting
    if _is_rate_limited(signal.symbol):
        logger.warning(f"Rate limit hit for {signal.symbol}")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Deduplication
    signal_hash = hashlib.md5(
        f"{signal.symbol}{signal.signal}{signal.timestamp}".encode()
    ).hexdigest()
    if _is_duplicate(signal_hash):
        logger.debug(f"Duplicate signal rejected: {signal.symbol} {signal.signal}")
        return {"status": "skipped", "reason": "Duplicate signal"}

    logger.info(f"Signal received: {signal.symbol} {signal.signal} | Confidence={signal.confidence}")

    # Process in background (non-blocking response)
    background_tasks.add_task(orchestrator.process_signal, signal.dict())

    return {
        "status": "received",
        "symbol": signal.symbol,
        "signal": signal.signal,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/kill-switch")
async def toggle_kill_switch(request: Request):
    """Emergency kill switch endpoint."""
    token = request.headers.get("X-Admin-Token")
    if not _validate_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.json()
    active = body.get("active", True)
    reason = body.get("reason", "Manual trigger")
    set_kill_switch(active, reason)
    logger.warning(f"Kill switch {'ACTIVATED' if active else 'DEACTIVATED'}: {reason}")
    return {"kill_switch": active, "reason": reason}


@app.get("/status")
async def get_status():
    """Current system status for monitoring."""
    from core.state_manager import get_daily_stats, count_active_trades
    stats = get_daily_stats()
    return {
        "active_trades": count_active_trades(),
        "daily_pnl": stats.get("net_pnl", 0),
        "daily_trades": stats.get("trades_taken", 0),
        "drawdown_pct": stats.get("current_drawdown_pct", 0),
        "kill_switch": is_kill_switch_active(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
