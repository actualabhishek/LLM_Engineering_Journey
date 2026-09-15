"""
core/config_manager.py
---------------------
Centralized configuration manager.
Loads config.json + .env variables.
Provides typed access to all settings.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"
STORAGE_DIR = BASE_DIR / "storage"
LOGS_DIR = STORAGE_DIR / "logs"
DATA_DIR = STORAGE_DIR / "data"


class ConfigManager:
    """
    Singleton configuration manager.
    Merges config.json with environment variable overrides.
    """
    _instance: Optional["ConfigManager"] = None
    _config: Dict[str, Any] = {}

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """Load configuration from JSON file and apply env overrides."""
        with open(CONFIG_PATH, "r") as f:
            self._config = json.load(f)

        # Apply critical env overrides
        self._config["mt5"]["login"] = int(os.getenv("MT5_LOGIN", self._config["mt5"]["login"]))
        self._config["mt5"]["password"] = os.getenv("MT5_PASSWORD", self._config["mt5"]["password"])
        self._config["mt5"]["server"] = os.getenv("MT5_SERVER", self._config["mt5"]["server"])
        self._config["webhook"]["secret_token"] = os.getenv(
            "WEBHOOK_SECRET_TOKEN", self._config["webhook"]["secret_token"]
        )
        self._config["ai_engine"]["anthropic_api_key"] = os.getenv("ANTHROPIC_API_KEY", "")
        self._config["ai_engine"]["openai_api_key"] = os.getenv("OPENAI_API_KEY", "")
        self._config["system"]["environment"] = os.getenv(
            "ENVIRONMENT", self._config["system"]["environment"]
        )
        self._config["logging"]["level"] = os.getenv("LOG_LEVEL", self._config["logging"]["level"])

        # Ensure storage directories exist
        STORAGE_DIR.mkdir(exist_ok=True)
        LOGS_DIR.mkdir(exist_ok=True)
        DATA_DIR.mkdir(exist_ok=True)

    def get(self, *keys: str, default: Any = None) -> Any:
        """Nested key access: config.get('risk', 'max_risk_per_trade_pct')"""
        val = self._config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k, default)
            else:
                return default
        return val

    # ---- Convenience properties ----

    @property
    def pairs(self) -> List[str]:
        return self._config["trading"]["pairs"]

    @property
    def lot_size(self) -> float:
        return self._config["trading"]["default_lot_size"]

    @property
    def magic_number(self) -> int:
        return self._config["mt5"]["magic_number"]

    @property
    def max_concurrent_trades(self) -> int:
        return self._config["trading"]["max_concurrent_trades"]

    @property
    def max_daily_drawdown_pct(self) -> float:
        return self._config["risk"]["max_daily_drawdown_pct"]

    @property
    def confidence_threshold(self) -> int:
        return self._config["ai_engine"]["confidence_threshold"]

    @property
    def webhook_secret(self) -> str:
        return self._config["webhook"]["secret_token"]

    @property
    def ai_enabled(self) -> bool:
        return self._config["ai_engine"]["enabled"]

    @property
    def news_enabled(self) -> bool:
        return self._config["news"]["enabled"]

    @property
    def full(self) -> Dict[str, Any]:
        """Return full config dict (read-only copy)."""
        return dict(self._config)


# Module-level singleton
config = ConfigManager()
