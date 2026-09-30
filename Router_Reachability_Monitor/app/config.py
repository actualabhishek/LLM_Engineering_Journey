"""Loads config.yaml (topology/thresholds) and .env (secrets) into one Settings object."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class Target(BaseModel):
    id: str
    hostname: str
    ip: str
    tcp_port: int = 22


class ProbeConfig(BaseModel):
    interval_s: int = 10
    icmp_count: int = 3
    icmp_timeout_s: float = 1.0
    fail_threshold: int = 3
    recover_threshold: int = 2
    tcp_fallback: bool = True


class FlapConfig(BaseModel):
    max_changes: int = 4
    window_s: int = 600


class AlertsConfig(BaseModel):
    escalate_call_after_s: int = 120
    repeat_every_s: int = 600
    channels: list[str] = []


class DashboardConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class AppConfig(BaseModel):
    """Topology and thresholds from config.yaml. No secrets here."""

    site: str
    timezone: str = "Asia/Kolkata"
    probe: ProbeConfig = ProbeConfig()
    flap: FlapConfig = FlapConfig()
    canaries: list[str] = ["1.1.1.1", "8.8.8.8"]
    targets: list[Target]
    alerts: AlertsConfig = AlertsConfig()
    dashboard: DashboardConfig = DashboardConfig()


class Secrets(BaseSettings):
    """Secrets from .env. Never logged, never hard-coded."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    callmebot_tg_user: str = ""
    callmebot_wa_phone: str = ""
    callmebot_wa_apikey: str = ""
    ntfy_topic: str = ""
    healthchecks_ping_url: str = ""
    dashboard_user: str = ""
    dashboard_pass: str = ""


class Settings(BaseModel):
    """Combined config.yaml + .env, accessed everywhere instead of scattered env reads."""

    app: AppConfig
    secrets: Secrets


def load_settings(config_path: Path = CONFIG_PATH) -> Settings:
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Settings(app=AppConfig(**raw), secrets=Secrets())
