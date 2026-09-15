"""
dashboard/app.py — ForexAI Trader Live Dashboard
=================================================
Thin entry point: page config, layout, and two auto-refreshing fragments.
All data access lives in dashboard/data.py, all rendering in
dashboard/components.py and dashboard/charts.py, log tailing in
dashboard/logs_viewer.py — this file just wires them together.
"""

import sys
import warnings
from pathlib import Path

import streamlit as st

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dashboard import components, charts, logs_viewer
from dashboard.data import (
    load_daily_stats, load_ai_decisions, load_kill_switch, load_trade_history,
    load_mt5_positions, load_mt5_account, load_candles_with_indicators,
)

PAIRS = ["EURUSD", "GBPUSD"]

st.set_page_config(
    page_title="ForexAI Trader",
    page_icon="\U0001F4C8",
    layout="wide",
    initial_sidebar_state="expanded",
)

_css_path = Path(__file__).parent / "assets" / "style.css"
if _css_path.exists():
    st.markdown(f"<style>{_css_path.read_text()}</style>", unsafe_allow_html=True)

# Streamlit 1.37+ renamed experimental_fragment -> fragment; support both
# without forcing a dependency bump on the currently pinned 1.36.0.
_fragment = getattr(st, "fragment", None) or st.experimental_fragment


st.title("\U0001F4C8 ForexAI Trader — Live Dashboard")


@_fragment(run_every="5s")
def sidebar_section() -> None:
    account = load_mt5_account()
    ks_active, ks_reason = load_kill_switch()
    components.render_sidebar(account, ks_active, ks_reason)


@_fragment(run_every="5s")
def live_section() -> None:
    stats = load_daily_stats()
    history = load_trade_history()
    positions = load_mt5_positions()
    ai_decisions = load_ai_decisions()

    components.render_kpi_row(stats, positions)
    st.divider()

    components.render_open_positions(positions)
    st.divider()

    candles_by_pair = {p: load_candles_with_indicators(p) for p in PAIRS}
    components.render_pair_panels(PAIRS, candles_by_pair, history)
    st.divider()

    components.render_equity_and_ai(history, positions, ai_decisions)
    st.divider()

    components.render_trade_history_table(history)
    st.divider()

    components.render_pair_performance_table(history)


@_fragment
def log_viewer_section() -> None:
    st.markdown("<div class='fai-section-title'>\U0001F4DC Logs</div>", unsafe_allow_html=True)
    col_a, col_b, col_c = st.columns([1, 1, 2])
    with col_a:
        log_name = st.selectbox("File", list(logs_viewer.AVAILABLE_LOGS.keys()), key="log_file_select")
    with col_b:
        level = st.selectbox("Level", ["ALL", "INFO", "WARNING", "ERROR", "DEBUG"], key="log_level_select")
    with col_c:
        search = st.text_input("Search", key="log_search_input", placeholder="filter by text…")

    path = logs_viewer.AVAILABLE_LOGS[log_name]
    lines = logs_viewer.tail_lines(path, max_lines=400)
    lines = logs_viewer.filter_lines(lines, level=level, search=search)

    st.caption(f"Showing last {len(lines)} matching lines from {log_name}")
    st.code("\n".join(lines[-200:]) or "(no matching log lines)", language="log")


with st.sidebar:
    sidebar_section()

live_section()
st.divider()
log_viewer_section()
