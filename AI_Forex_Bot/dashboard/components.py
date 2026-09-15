"""
dashboard/components.py
-------------------------
One render_* function per dashboard section, split out of the old
monolithic app.py. Pure Streamlit rendering — data comes in as arguments,
nothing in here reads files or hits MT5 directly (see dashboard/data.py).
"""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from dashboard import theme, charts
from dashboard.data import get_session_and_mtf_snapshot


# ── Sidebar ──────────────────────────────────────────────────────────────

def render_sidebar(account: dict, ks_active: bool, ks_reason: str) -> None:
    """Renders sidebar content. Caller must already be inside a
    `with st.sidebar:` block — a fragment function cannot open that context
    itself (Streamlit restriction), so this assumes it, it doesn't create it."""
    st.markdown("## \U0001F4C8 ForexAI Trader")
    st.caption("EUR/USD + GBP/USD · 15m intraday")
    st.markdown("---")

    session_info = get_session_and_mtf_snapshot("EURUSD")
    now_utc = datetime.now(timezone.utc)
    st.metric("Session", session_info.get("session", "?").replace("_", " ").title())
    st.metric("UTC Time", now_utc.strftime("%H:%M:%S"))
    st.caption(f"Flat-close cutover: 21:00 UTC ({_minutes_to_cutover(now_utc)} left)")

    if account:
        st.markdown("---")
        st.markdown("**Account**")
        st.metric("Balance", f"${account.get('balance', 0):.2f}")
        st.metric("Equity", f"${account.get('equity', 0):.2f}",
                  delta=f"{account.get('profit', 0):+.2f}")
        st.metric("Free Margin", f"${account.get('free_margin', 0):.2f}")

    st.markdown("---")
    if ks_active:
        st.error(f"\U0001F6A8 KILL SWITCH ACTIVE\n{ks_reason}")
    else:
        st.success("✅ System Running")

    st.markdown("---")
    if st.button("\U0001F504 Force Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("Live sections auto-refresh every 5s")


def _minutes_to_cutover(now_utc: datetime) -> str:
    cutover_minutes = 21 * 60
    now_minutes = now_utc.hour * 60 + now_utc.minute
    remaining = cutover_minutes - now_minutes
    if remaining < 0:
        remaining += 24 * 60
    return f"{remaining // 60}h{remaining % 60:02d}m"


# ── KPI row ──────────────────────────────────────────────────────────────

def render_kpi_row(stats: dict, positions: list, max_concurrent: int = 2) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        pnl = stats.get("net_pnl", 0)
        st.metric("Today's P&L", f"${pnl:+.2f}")

    with c2:
        taken = stats.get("trades_taken", 0)
        won = stats.get("trades_won", 0)
        wr = won / taken * 100 if taken else 0
        st.metric("Win Rate", f"{wr:.0f}%", f"{won}W / {taken - won}L")

    with c3:
        st.metric("Open Trades", f"{len(positions)} / {max_concurrent}")

    with c4:
        gp = stats.get("gross_profit", 0)
        gl = stats.get("gross_loss", 0)
        pf = gp / gl if gl > 0 else 0.0
        st.metric("Profit Factor", f"{pf:.2f}" if pf > 0 else "—")

    with c5:
        dd = stats.get("current_drawdown_pct", 0)
        max_dd = 3.0
        st.markdown("<div class='fai-muted'>Daily Drawdown</div>", unsafe_allow_html=True)
        st.plotly_chart(charts.render_drawdown_gauge(dd, max_dd),
                         use_container_width=True, config={"displayModeBar": False},
                         key=f"dd_gauge_{id(stats)}")


# ── Open positions ───────────────────────────────────────────────────────

def render_open_positions(positions: list) -> None:
    st.markdown("<div class='fai-section-title'>\U0001F538 Live Open Positions</div>", unsafe_allow_html=True)

    if not positions:
        st.info("No open positions right now. Bot is scanning for setups every 5 minutes.")
        return

    for pos in positions:
        direction = pos.get("direction", "BUY")
        pnl = pos.get("floating_pnl", 0)
        pnl_c = theme.pnl_color(pnl)
        dur = pos.get("duration_min", 0)
        dur_str = f"{dur}m" if dur < 60 else f"{dur // 60}h {dur % 60}m"

        with st.container():
            st.markdown("<div class='fai-card'>", unsafe_allow_html=True)
            col_a, col_b, col_c, col_d, col_e, col_f = st.columns([1.5, 1, 1.2, 1.5, 1.5, 2])

            with col_a:
                dir_color = theme.PRIMARY if direction == "BUY" else theme.AMBER
                st.markdown(
                    f"<span class='fai-pill' style='background:{dir_color}22;color:{dir_color}'>"
                    f"{direction}</span> &nbsp;**{pos.get('pair')}**",
                    unsafe_allow_html=True,
                )
                st.caption(f"{pos.get('lots', 0.01)} lots · open {dur_str}")

            with col_b:
                st.metric("Open", f"{pos.get('open_price', 0):.5f}")

            with col_c:
                st.metric("Current", f"{pos.get('current_price', 0):.5f}")

            with col_d:
                st.markdown(
                    f"<span style='color:{pnl_c};font-weight:600'>${pnl:+.2f}</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"{pos.get('floating_pips', 0):+.1f} pips")

            with col_e:
                st.markdown(f"**SL** `{pos.get('sl')}` &nbsp; **TP** `{pos.get('tp')}`")
                st.caption(f"SL: {pos.get('sl_pips', 0):.1f}p · TP: {pos.get('tp_pips', 0):.1f}p")

            with col_f:
                tpp = pos.get("tp_progress", 0)
                st.caption("Progress to TP")
                st.progress(min(tpp / 100, 1.0))
                st.caption(f"{tpp:.1f}% of the way to TP")

            st.markdown("</div>", unsafe_allow_html=True)


# ── Per-pair candlestick panels ──────────────────────────────────────────

def render_pair_panels(pairs: list, candles_by_pair: dict, trade_history: pd.DataFrame) -> None:
    st.markdown("<div class='fai-section-title'>\U0001F4C9 Pair Charts</div>", unsafe_allow_html=True)
    cols = st.columns(len(pairs)) if pairs else []
    for col, pair in zip(cols, pairs):
        with col:
            session_info = get_session_and_mtf_snapshot(pair)
            st.caption(
                f"**{pair}** · session: {session_info.get('session', '?').replace('_', ' ')} "
                f"· min conf: {session_info.get('min_confidence_required', '?')}"
            )
            df = candles_by_pair.get(pair)
            fig = charts.render_pair_chart(pair, df, trade_history)
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False},
                                 key=f"chart_{pair}")
            else:
                st.info(f"No live candle data for {pair} yet.")


# ── Equity curve + AI decisions ──────────────────────────────────────────

def render_equity_and_ai(history: pd.DataFrame, positions: list, ai_decisions: list) -> None:
    col_eq, col_ai = st.columns([2, 1])

    with col_eq:
        st.markdown("<div class='fai-section-title'>\U0001F4CA Equity Curve</div>", unsafe_allow_html=True)
        if not history.empty and "profit_usd" in history.columns:
            h = history.dropna(subset=["profit_usd"]).copy()
            if "close_time" in h.columns:
                h = h.sort_values("close_time")
            h["cumulative_pnl"] = h["profit_usd"].cumsum()
            total_float = sum(p.get("floating_pnl", 0) for p in positions)
            if total_float != 0:
                last_pnl = h["cumulative_pnl"].iloc[-1] if len(h) else 0
                extra = pd.DataFrame({"cumulative_pnl": [last_pnl + total_float]})
                h = pd.concat([h[["cumulative_pnl"]], extra], ignore_index=True)
            st.line_chart(h[["cumulative_pnl"]], use_container_width=True)
        else:
            float_total = sum(p.get("floating_pnl", 0) for p in positions)
            if float_total != 0:
                st.line_chart(pd.DataFrame({"floating_pnl": [0, float_total]}))
            else:
                st.info("Equity curve will appear after the first closed trade.")

    with col_ai:
        st.markdown("<div class='fai-section-title'>\U0001F916 AI Decisions</div>", unsafe_allow_html=True)
        if ai_decisions:
            for dec in reversed(ai_decisions[-10:]):
                score = dec.get("score", dec.get("final_score", 0))
                decision = dec.get("decision", "SKIP")
                pair = dec.get("pair", "?")
                direction = dec.get("direction", "")
                llm_icon = "\U0001F9E0" if dec.get("llm_used") else "⚡"
                is_trade = decision in ("TAKE", "STRONG_TAKE")
                color = theme.GREEN if is_trade else theme.RED if decision == "SKIP" else theme.AMBER
                st.markdown(
                    f"<div class='fai-decision' style='--fai-color:{color}'>"
                    f"{llm_icon} <b>{pair}</b> {direction} "
                    f"→ <b style='color:{color}'>{decision}</b> "
                    f"<span class='fai-muted'>· {score:.0f}pts</span></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("AI decisions appear as the scanner runs.")


# ── Trade history table ──────────────────────────────────────────────────

def render_trade_history_table(history: pd.DataFrame) -> None:
    st.markdown("<div class='fai-section-title'>\U0001F4CB Recent Trade History</div>", unsafe_allow_html=True)

    if history.empty:
        st.info("Trade history appears after the first trade closes.")
        return

    show_cols = [c for c in
        ["close_time", "pair", "direction", "lots", "open_price",
         "close_price", "pips", "profit_usd", "exit_reason", "confidence"]
        if c in history.columns]
    if not show_cols:
        show_cols = history.columns.tolist()

    disp = history[show_cols].copy().iloc[::-1].reset_index(drop=True)

    if "profit_usd" in disp.columns:
        disp["profit_usd"] = disp["profit_usd"].apply(
            lambda x: f"+${float(x):.2f}" if pd.notna(x) and x != "" and float(x) > 0
            else f"-${abs(float(x)):.2f}" if pd.notna(x) and x != "" and float(x) < 0
            else "pending"
        )
    if "pips" in disp.columns:
        disp["pips"] = disp["pips"].apply(
            lambda x: f"+{float(x):.1f}" if pd.notna(x) and x != "" and float(x) > 0
            else f"{float(x):.1f}" if pd.notna(x) and x != "" else "pending"
        )
    if "confidence" in disp.columns:
        disp["confidence"] = disp["confidence"].apply(
            lambda x: f"{float(x):.0f}" if pd.notna(x) and x != "" else "—"
        )
    if "close_time" in disp.columns:
        disp["close_time"] = disp["close_time"].apply(
            lambda x: pd.to_datetime(x, errors="coerce").strftime("%m-%d %H:%M")
            if pd.notna(x) and x != "" and x != "None" else "open"
        )
    if "close_price" in disp.columns:
        disp["close_price"] = disp["close_price"].apply(
            lambda x: f"{float(x):.5f}" if pd.notna(x) and x != "" and x != "None" else "open"
        )

    exit_reasons = disp.get("exit_reason", [])
    n_sl_tp = len([x for x in exit_reasons if "sl_tp" in str(x)])
    n_cutover = len([x for x in exit_reasons if "flat_close_cutover" in str(x)])
    st.caption(
        f"Showing {len(disp)} trades · SL/TP: {n_sl_tp} · "
        f"Flat-close cutover: {n_cutover}"
    )
    st.dataframe(disp, use_container_width=True, hide_index=True,
                 height=min(600, 35 * len(disp) + 38))


# ── Pair performance table ────────────────────────────────────────────────

def render_pair_performance_table(history: pd.DataFrame) -> None:
    st.markdown("<div class='fai-section-title'>\U0001F4C8 Pair Performance (Closed Trades)</div>",
                unsafe_allow_html=True)

    if history.empty or "profit_usd" not in history.columns:
        st.info("Pair performance will populate after trades close.")
        return

    h_closed = history.dropna(subset=["profit_usd"])
    if h_closed.empty or "pair" not in h_closed.columns:
        st.info("Pair performance will populate after trades close.")
        return

    pair_stats = h_closed.groupby("pair").agg(
        Trades=("profit_usd", "count"),
        Net_PnL=("profit_usd", "sum"),
        Win_Rate=("profit_usd", lambda x: f"{(x > 0).mean() * 100:.0f}%"),
        Avg_PnL=("profit_usd", "mean"),
    ).round(2).reset_index()

    def color_pnl(val):
        try:
            v = float(str(val).replace("$", "").replace("+", ""))
            return f"color: {theme.GREEN}" if v > 0 else f"color: {theme.RED}" if v < 0 else ""
        except Exception:
            return ""

    st.dataframe(
        pair_stats.style.map(color_pnl, subset=["Net_PnL", "Avg_PnL"]),
        use_container_width=True,
        hide_index=True,
    )
