"""
dashboard/theme.py
-------------------
Shared color constants, matching .streamlit/config.toml's [theme] section.
Single source of truth so components.py and charts.py never hardcode colors
independently (the old app.py scattered hex literals across ~5 places).
"""

BG = "#0e1117"
SURFACE = "#161b22"
SURFACE_ALT = "#1c2128"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"

PRIMARY = "#3b82f6"
GREEN = "#22c55e"
RED = "#ef4444"
AMBER = "#f59e0b"
PURPLE = "#a855f7"

EMA_COLORS = {"ema9": AMBER, "ema21": PRIMARY, "ema50": PURPLE}


def pnl_color(value: float) -> str:
    return GREEN if value >= 0 else RED


def pnl_badge(value: float) -> str:
    return "\U0001F7E2" if value >= 0 else "\U0001F534"  # green/red circle
