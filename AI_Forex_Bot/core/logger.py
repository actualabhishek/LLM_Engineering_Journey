"""
core/logger.py
--------------
Production-grade logging system.
- Execution log (all trades, signals)
- Error log (exceptions only)
- AI decisions log (LLM reasoning)
- Async-safe: execution engine never blocks on log I/O
"""

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "storage" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _create_rotating_handler(
    filename: str, level: int = logging.DEBUG, max_mb: int = 50, backup: int = 5
) -> logging.handlers.RotatingFileHandler:
    handler = logging.handlers.RotatingFileHandler(
        LOGS_DIR / filename,
        maxBytes=max_mb * 1024 * 1024,
        backupCount=backup,
        encoding="utf-8",
    )
    handler.setLevel(level)
    return handler


def _setup_formatter(include_module: bool = True) -> logging.Formatter:
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s" if include_module \
        else "%(asctime)s | %(levelname)-8s | %(message)s"
    return logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")


def get_logger(name: str, level_str: str = "INFO") -> logging.Logger:
    """
    Get a named logger with both console and file output.
    Call once per module: logger = get_logger(__name__)
    """
    level = getattr(logging, level_str.upper(), logging.INFO)
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.DEBUG)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(_setup_formatter())
    logger.addHandler(console)

    # Execution log (INFO+)
    exec_handler = _create_rotating_handler("execution.log", logging.INFO)
    exec_handler.setFormatter(_setup_formatter())
    logger.addHandler(exec_handler)

    # Error log (ERROR+)
    err_handler = _create_rotating_handler("errors.log", logging.ERROR)
    err_handler.setFormatter(_setup_formatter())
    logger.addHandler(err_handler)

    return logger


# ---- Specialized AI Decision Logger ----

class AIDecisionLogger:
    """
    Structured JSON logger for AI reasoning decisions.
    Written to ai_decisions.log as newline-delimited JSON.
    Designed to be non-blocking; wraps write in try/except.
    """
    _path = LOGS_DIR / "ai_decisions.log"

    @classmethod
    def log(
        cls,
        pair: str,
        signal_type: str,
        confidence: float,
        reasoning: str,
        indicators: Optional[Dict[str, Any]] = None,
        llm_used: bool = False,
        decision: str = "SKIP",
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pair": pair,
            "signal_type": signal_type,
            "confidence": confidence,
            "decision": decision,
            "llm_used": llm_used,
            "reasoning": reasoning,
            "indicators": indicators or {},
        }
        try:
            with open(cls._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass  # Never block execution on log failure


# ---- Trade Event Logger ----

class TradeLogger:
    """
    Appends trade events to trade_events.log as JSON lines.
    Non-blocking; silent on failure.
    """
    _path = LOGS_DIR / "trade_events.log"

    @classmethod
    def log(cls, event: str, data: Dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **data,
        }
        try:
            with open(cls._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass
