"""
dashboard/charts.py
--------------------
Real Plotly candlestick charts — the dashboard's biggest functional gap
before this redesign: `plotly` was a declared-but-unused dependency and the
only chart was a bare st.line_chart equity curve. This finally uses it for
per-pair OHLC charts with EMA/Supertrend overlays and entry/exit markers
pulled from trade history.
"""

import pandas as pd
import plotly.graph_objects as go

from dashboard import theme


def render_pair_chart(pair: str, df: pd.DataFrame, trade_history: pd.DataFrame):
    """Build a candlestick figure for `pair`. Returns None if no data."""
    if df is None or df.empty:
        return None

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name=pair,
        increasing_line_color=theme.GREEN, increasing_fillcolor=theme.GREEN,
        decreasing_line_color=theme.RED, decreasing_fillcolor=theme.RED,
        showlegend=False,
    ))

    for col, label in (("ema9", "EMA9"), ("ema21", "EMA21"), ("ema50", "EMA50")):
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col], mode="lines", name=label,
                line=dict(width=1.3, color=theme.EMA_COLORS[col]),
            ))

    if "supertrend" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["supertrend"], mode="lines", name="Supertrend",
            line=dict(width=1, color=theme.MUTED, dash="dot"),
        ))

    _add_trade_markers(fig, pair, df, trade_history)

    fig.update_layout(
        height=380,
        margin=dict(l=10, r=10, t=36, b=10),
        paper_bgcolor=theme.SURFACE,
        plot_bgcolor=theme.SURFACE,
        font=dict(color=theme.TEXT, size=11),
        xaxis=dict(gridcolor=theme.BORDER, rangeslider=dict(visible=False)),
        yaxis=dict(gridcolor=theme.BORDER),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        title=dict(text=pair, font=dict(size=14, color=theme.TEXT), x=0.01),
    )
    return fig


def _add_trade_markers(fig: go.Figure, pair: str, df: pd.DataFrame, trade_history: pd.DataFrame) -> None:
    if trade_history is None or trade_history.empty or "pair" not in trade_history.columns:
        return
    pair_trades = trade_history[trade_history["pair"] == pair]
    if pair_trades.empty:
        return

    window_start, window_end = df.index.min(), df.index.max()
    entries_x, entries_y = [], []
    exits_x, exits_y, exits_color = [], [], []

    for _, t in pair_trades.iterrows():
        open_time = pd.to_datetime(t.get("open_time"), errors="coerce", utc=True)
        if pd.notna(open_time) and window_start <= open_time <= window_end and t.get("open_price"):
            entries_x.append(open_time)
            entries_y.append(t.get("open_price"))

        close_time = pd.to_datetime(t.get("close_time"), errors="coerce", utc=True)
        profit = pd.to_numeric(t.get("profit_usd"), errors="coerce")
        if pd.notna(close_time) and window_start <= close_time <= window_end and t.get("close_price"):
            exits_x.append(close_time)
            exits_y.append(t.get("close_price"))
            exits_color.append(theme.GREEN if pd.notna(profit) and profit > 0 else theme.RED)

    if entries_x:
        fig.add_trace(go.Scatter(
            x=entries_x, y=entries_y, mode="markers", name="Entry",
            marker=dict(symbol="triangle-up", size=11, color=theme.PRIMARY,
                        line=dict(width=1, color=theme.TEXT)),
        ))
    if exits_x:
        fig.add_trace(go.Scatter(
            x=exits_x, y=exits_y, mode="markers", name="Exit",
            marker=dict(symbol="x", size=9, color=exits_color, line=dict(width=1)),
        ))


def render_drawdown_gauge(current_pct: float, max_pct: float):
    """Gauge for the daily drawdown circuit breaker — now meaningful since
    Iteration 1 wired core.state_manager.update_drawdown() into the live
    monitor loop (it was previously never called, so this number was
    effectively always 0)."""
    color = theme.RED if current_pct >= max_pct * 0.8 else (
        theme.AMBER if current_pct >= max_pct * 0.5 else theme.GREEN
    )
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=current_pct,
        number={"suffix": "%", "font": {"color": theme.TEXT, "size": 22}},
        gauge={
            "axis": {"range": [0, max(max_pct * 1.3, 1)], "tickcolor": theme.MUTED},
            "bar": {"color": color},
            "bgcolor": theme.SURFACE,
            "borderwidth": 0,
            "steps": [
                {"range": [0, max_pct], "color": theme.SURFACE_ALT},
                {"range": [max_pct, max(max_pct * 1.3, 1)], "color": "#3a1a1a"},
            ],
            "threshold": {"line": {"color": theme.RED, "width": 2}, "value": max_pct},
        },
    ))
    fig.update_layout(
        height=140, margin=dict(l=20, r=20, t=10, b=10),
        paper_bgcolor=theme.SURFACE, font=dict(color=theme.TEXT),
    )
    return fig
