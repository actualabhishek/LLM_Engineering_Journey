# Change History Log

This file records every change made to the program, with each entry timestamped.

---

## 2026-09-13 13:26:56

Created `prompt.md` and `hist.md` in the project root to establish an ongoing prompt/change log. Logged the triggering prompt (this setup request) as the first entry in `prompt.md`.

---

## 2026-09-13 14:09:37 — Iteration 1: Core rewire (bug fixes, pair narrowing, exit cutover, sizing)

Full discovery (3 parallel research passes over signal engine, execution/risk, and dashboard) plus forex-mechanics research were done first; a plan was written, reviewed against the live code, and approved before any file was touched. Summary of research/plan: EUR/USD and GBP/USD are the best-fit majors for 15m intraday trading (tightest spreads/deepest liquidity, cleanest event-driven moves); London pre-overlap hours form the cleanest early trend, the London-NY overlap has the deepest liquidity but sharpest whipsaws. Decisions locked in with the user: narrow to EUR/USD+GBP/USD, strict same-day flat-close at 21:00 UTC, equity-based position sizing, keep 3%/15% drawdown thresholds unchanged for now, enhance the existing Streamlit dashboard rather than rebuild it.

**Bug fixes:**
- `core/state_manager.py::update_drawdown()` was defined but never called anywhere — the daily/weekly drawdown circuit breakers in `risk_engine.can_take_trade()` have likely never actually tripped in live trading. Wired it into `mt5_execution/trade_monitor.py`'s 30s monitor loop (using live **equity**) and seeded it once in `trading_orchestrator.run_system()` after MT5 connects.
- `backtesting/replay_backtest.py` had a broken import (`is_choppy_market` didn't exist in `strategies/signal_engine.py`) — the "faithful" backtester was completely unrunnable. Added `is_choppy_market()` to `signal_engine.py` (ADX-based, mirrors the existing check in `confidence_engine.py`).
- Fixed a second, separate crash in `replay_backtest.py`: `print()` calls with Unicode box-drawing/em-dash characters (`─`, `—`) raised `UnicodeEncodeError` on this machine's Windows cp1252 console, so the backtester crashed after finishing every run, right before printing results. Replaced with ASCII equivalents.
- Removed `TradingOrchestrator._is_trading_allowed_now()` — a dead, unused duplicate of `core/session_manager.is_trading_time()`.
- Removed two stray brace-expansion artifact directories at the repo root and under `storage/` (empty, unused — leftover from a `mkdir {a,b,c}` typo).
- Moved the stray root-level `trade_history.csv` (a raw MT5 deal-export in a different schema, read by no code) to `storage/data/archive/legacy_mt5_export_trade_history.csv` so it stops looking like a second live data source next to the real `storage/data/trade_history.csv`.
- **Security**: removed plaintext MT5 login/password and the webhook secret token from `config/config.json` (replaced with placeholders — `.env` already overrides all of these at load time, confirmed nothing else reads the JSON values directly). Added a `.gitignore` (covering `.env`, `storage/data`, `storage/logs`, etc.) as a prerequisite for whenever this becomes a git repo.

**Pair universe narrowed to EUR/USD + GBP/USD** (`config/config.json: trading.pairs`), dropping GBPJPY/EURJPY/AUDUSD/USDCAD from live trading per the research recommendation (kept in a code comment for easy re-enabling later). Trimmed the now-dormant pairs out of `core/session_manager.get_best_pairs_for_session()` and `backtesting/replay_backtest.py`'s default `PAIRS`; commented `risk_engine.SPREAD_USD_PER_PIP_01_LOT` to mark which entries are live vs. dormant. Set `trading.max_concurrent_trades` 3 → 2 (documentation-consistency only — the existing one-position-per-pair rule already capped this at 2 with only 2 pairs live).

**Strict same-day flat-close at 21:00 UTC** — replaces the old behavior where positions could hold up to 24h and only got force-closed early if stuck at breakeven/loss. `mt5_execution/trade_monitor.py` now force-closes every open position once wall-clock UTC time passes `risk.flat_close_cutover_utc` (new config key, "21:00"), via a new shared `_close_all(reason)` helper (also now used by the kill-switch path). Added a pre-trade gate in `trading_orchestrator.py` (`_cutover_proximity_ok`) blocking new entries within `risk.min_minutes_before_cutover_for_new_trade` (30) minutes of the cutover. Removed the old hardcoded `max_hours=24` time-exit call. Extended `backtesting/replay_backtest.py` to simulate the same cutover rule bar-by-bar (new `flat_close_cutover_exits`/`flat_close_cutover_pct` metrics) so backtests reflect real intraday behavior.

**Position sizing refinements**: switched the sizing input from account balance to **equity** in `trading_orchestrator.py` (reacts to floating P&L in real time, consistent with the drawdown fix above). Added `mt5_engine.get_pip_value_usd_per_lot()` (live MT5 tick value/size, replacing the hand-maintained approximation table as the primary source — the static dict is now only a fallback) and `mt5_engine.get_margin_usd_per_lot()`. Added a margin sanity clamp to `risk_engine.calculate_position_size()` (new `risk.margin_safety_factor: 0.8`) that can only reduce the risk-based lot size, never increase it.

**Backtester CLI**: `main.py --mode backtest` now runs the real strategy backtester (`backtesting/replay_backtest.py`) instead of the old simplified/non-representative one; the old one is still available via `--mode legacy-backtest`. Added `--pair`/`--days`/`--balance`/`--spread` CLI flags.

**Verification performed:**
- All edited files byte-compile cleanly; `config.json` validated as well-formed JSON.
- `pytest tests/` still shows the same pre-existing 25 failed / 10 passed (stale test suite against an old API — no new regressions introduced; rewriting these is planned for Iteration 2).
- Ran `python main.py --mode backtest --pair EURUSD --days 30` against the live MT5 demo account end-to-end: 81 trades, 63.0% win rate, net +$171.92 (+34.4% ROI on $500), profit factor 1.76, max drawdown 6.6%, 17.3% of trades exited via the new flat-close cutover.
- Ran the same for GBPUSD: 90 trades, 56.7% win rate, net -$34.14 (-6.8% ROI), profit factor 0.86 — GBPUSD is currently net-negative with the pre-Iteration-2 signal engine; this is exactly the kind of result the Iteration 2 divergence/retest trigger + A/B backtest is meant to test and potentially improve.
- Manually unit-tested `update_drawdown()` (peak tracking + % calc) and the new margin clamp in isolation — both behave as designed.

**Risk-relevant note for the user**: the daily (3%) and weekly (15%) drawdown circuit breakers will now actually function for the first time in this bot's history (previously silently inert). Equity-based sizing means lot sizes will now shrink automatically during an open floating loss. Recommend watching the demo account for 1-2 weeks to confirm both behave as expected before treating these thresholds as final (per the approved plan).

Next: Iteration 2 (signal engine redesign — RSI-divergence/retest trigger, early-entry integration, test suite rewrite, A/B backtest).

---

## 2026-09-13 14:39:10 — Iteration 2: Signal/entry redesign + validation

**Migrated the orphaned `strategies/signal_engine_v2.py`** (built, never wired into the live pipeline) into a new `strategies/divergence_retest.py`, keeping only its genuinely useful mechanism — RSI divergence as a leading signal — and dropping its "fire on divergence alone" raw form in favor of a two-step version: detect the divergence, then require a retest/pin-bar/engulfing rejection at that level before treating it as tradeable. Deleted `signal_engine_v2.py` (confirmed nothing imported it).

**Added a 7th trigger** `trigger_divergence_retest()` to the live `strategies/signal_engine.py`, competing on quality score like the existing 6 (liquidity sweep, CHOCH, BOS, momentum expansion, EMA pullback, compression breakout) — gated by a new feature flag `signal_engine.enable_divergence_retest_trigger` specifically so it could be A/B-tested in isolation. Also added: an opposing-divergence soft quality penalty on other triggers (`signal_engine.opposing_divergence_penalty`), a choppy-market confidence dampener using the new `is_choppy_market()` (built in Iteration 1 to fix the backtester), and — a real bug fix — wrapped the previously unconditional D1+H4 hard block in `config.get("signal_engine", "require_d1_h4_alignment")`, which existed in config.json but was never actually read by the code (confirmed by grep and a spot-check of the live file before fixing). Corrected the file's docstring, which claimed HTF context "never blocks" a trade while an unconditional block existed a few lines below it.

**Early/false-entry integration** (`strategies/early_entry.py`, `strategies/precision_entry.py`): added an optional `divergence_context` parameter to `run_early_entry_analysis()` so a confirmed divergence+retest isn't redundantly re-delayed by independent timing checks that already happened as part of retest confirmation. Renamed `precision_entry.check_momentum_divergence()` → `check_chase_divergence()` to disambiguate it from the new proactive divergence trigger (same underlying RSI-divergence pattern, opposite role: one avoids chasing a move, the other is a reason to enter). Promoted volume confirmation from a soft score to a hard requirement specifically for the divergence/retest trigger type (a retest with no volume confirmation is the classic false-retest failure mode) — the other 6 triggers are untouched by this.

**Test suite rewrite** (`tests/test_core_modules.py`): rewritten against the real current API (previous version tested a speculative API that never matched the implementation — e.g. `ConfidenceEngine.compute()` vs the real `.score()`, a `SessionManager`/`StateManager` class that doesn't exist). Result: **56 passed, 0 failed**, up from 25 failed / 10 passed. Added `tests/test_divergence_retest.py` (divergence/retest detection logic, the now-config-gated D1+H4 block, a BUY/SELL trigger symmetry guard) and `tests/test_flat_close.py` (mocks wall-clock time crossing the Iteration-1 flat-close cutover and asserts every open position gets force-closed — the single highest-value new test given it's a live-trading-affecting behavior change).

**A/B backtest — go/no-go on the new trigger:** ran EUR/USD and GBP/USD over both 90-day and 180-day windows with `enable_divergence_retest_trigger` on vs. off. Result, consistent across all 4 comparisons: **disabling the new trigger performed slightly better** (e.g. EURUSD 180d: $481.92 net / PF 1.21 disabled vs. $378.57 net / PF 1.16 enabled). Isolating further, the opposing-divergence penalty mechanism (always-on, independent of the trigger flag, affecting the other 6 triggers' scores whenever any divergence is detected — confirmed or not) also tested slightly negative on its own: setting `opposing_divergence_penalty` to 0 improved EURUSD 180d results further, to $514.12 net / PF 1.21. The new trigger itself fired rarely by design (1-5 times per 90-180 day window per pair, since it requires both a divergence AND a confirmed retest) and its own trades were close to breakeven-to-positive in this small sample (e.g. GBPUSD 180d: 5 trades, 40% win rate, net +$0.32) — not clearly harmful on their own, but too small a sample to claim a real edge yet either.

**Decision: shipped OFF by default** — `enable_divergence_retest_trigger: false`, `opposing_divergence_penalty: 0` in `config/config.json`. The code is fully built, tested, and one config flip away from re-enabling; this defers the "does it actually help" call to real evidence (continued backtesting on more history, or demo-account data) rather than shipping it on based on design intuition alone that the backtest doesn't yet support. The D1+H4 config-gate fix, the choppy-market dampener, and the disambiguation/volume-hardening changes to the existing checks all stay live regardless of this flag — only the new 7th trigger and its associated penalty are currently dormant.

**Verification performed:** all edited files byte-compile cleanly; full test suite (`pytest tests/`) — 56 passed, 0 failed; 8 replay-backtest runs across 2 pairs × 2 windows × on/off states, plus 2 more isolating the penalty mechanism, all against live MT5 demo history.

Next: Iteration 3 (dashboard rebuild — lowest trading-risk, purely observational/UI).

---

## 2026-09-13 17:01:47 — Iteration 3: Dashboard rebuild

**Split the old 405-line monolithic `dashboard/app.py`** into a package: `data.py` (all file/MT5 loaders, unchanged logic), `components.py` (one render function per section), `charts.py` (new), `logs_viewer.py` (new), `theme.py` (shared color constants), `assets/style.css` (layout polish), plus a new `.streamlit/config.toml` for a real dark theme — replacing the 100%-default Streamlit light theme that was the only look the dashboard ever had.

**Real Plotly candlestick charts** (`dashboard/charts.py`) — finally using the `plotly` dependency that had been declared but unused since the project began. One panel per pair (EURUSD, GBPUSD — practical now that Iteration 1 narrowed the universe to 2), with EMA9/21/50 and Supertrend overlays computed live from MT5 candle data, plus entry/exit markers pulled from `trade_history.csv` (triangle-up/down for entries, X for exits, colored by win/loss). Also added a Plotly gauge for the daily drawdown circuit breaker, which is only meaningful now that Iteration 1 actually wired it up (it read 0% for the bot's entire history before that fix).

**Log viewer** (`dashboard/logs_viewer.py`) — surfaces `storage/logs/execution.log` and `errors.log`, which were being written all along but never shown anywhere. Tails from the end of the file (seek-from-end, chunked) rather than loading the ~17MB file whole, with a level filter and text search.

**Replaced the `time.sleep(5); st.rerun()` auto-refresh anti-pattern** with `st.experimental_fragment(run_every="5s")` (the installed Streamlit is 1.36.0, which has the `experimental_fragment` name — `st.fragment` was only promoted out of experimental in 1.37+; added a one-line compatibility shim so this upgrades itself automatically if Streamlit is later bumped). Split into two independent fragments — one for the live trading data (KPIs, positions, charts, equity/AI feed, trade history), one for the log viewer — so interacting with the log filter/search doesn't reset the rest of the page, and vice versa. Hit one real Streamlit constraint along the way: a fragment function cannot itself open a `with st.sidebar:` block; fixed by establishing that context at the call site and giving the sidebar its own fragment.

**Session-quality display** now reads from `core.session_manager.get_session_info()` (single source of truth) instead of the dashboard's own separate, slightly-divergent `get_session(hour)` re-implementation the old `app.py` had.

**Verification performed:** all dashboard files byte-compile cleanly. Ran the dashboard for real against the live MT5 connection (`streamlit run dashboard/app.py`) and drove it with a browser: confirmed the dark theme and custom CSS render, both pair candlestick charts pull live MT5 candles with EMA/Supertrend overlays, the KPI row and drawdown gauge render, the sidebar's UTC clock and cutover countdown tick independently every 5s without resetting scroll position (the exact problem the old sleep+rerun pattern had), and the log viewer's file/level/search filters actually filter — including surfacing a real log line from testing earlier today (`risk_management.risk_engine | Position size EURUSD: margin clamp reduced lot 0.20 -> 0.0...`), confirming the log viewer, the trading engine, and the file-based logging are all correctly wired together end to end. Added `tests/test_dashboard_data.py` (7 tests) covering the pure-function loaders' missing-file and malformed-data fallback paths.

**Full test suite: 63 passed, 0 failed** (`pytest tests/`), up from the original 25 failed / 10 passed baseline.

This closes out the 3-iteration plan: Iteration 1 (core bug fixes, pair narrowing, exit cutover, sizing refinements), Iteration 2 (signal engine redesign with an honest A/B backtest verdict), Iteration 3 (dashboard). No new dependencies were added in any iteration — everything shipped used packages already in `requirements.txt`.

---

## 2026-09-13 17:30:47 — $100/day target feasibility analysis

User asked to adjust the bot to realistically target a **minimum** $100/day (10%/day) on a $1,000 account with losses kept minimal, then validate honestly via backtest — explicitly not by raising risk-per-trade to force the number, and not by cherry-picking a favorable backtest window.

**Code change** (`backtesting/replay_backtest.py` — the only file touched, no live trading logic changed):
- Added real `open_time`/`close_time` timestamps to every simulated trade (previously only integer bar indices were stored, making day-by-day analysis impossible).
- Added `_daily_metrics()`: groups closed trades by calendar day and computes trading days, days hitting the target, days positive/negative, avg/median daily P&L, daily P&L std dev, best/worst day, and max consecutive losing days — printed as a new "DAILY PERFORMANCE" block, plus a "COMBINED DAILY PERFORMANCE" block across both pairs together when running the default multi-pair mode (this is the number that actually answers "does the account hit $100/day", since the live bot trades both pairs concurrently out of one balance).
- Added `--daily-target` (default 100) and `--risk-mult` (in-process only, never touches `config.json`) CLI flags, wired through `main.py --mode backtest` too.

**No changes to `config/config.json` or any risk parameter** — per the explicit constraint, live risk-per-trade tiers stay at 0.5%/1.0%/1.5%.

**Backtest run**: 270 days (~9 months) ending today, EUR/USD + GBP/USD together, $1,000 starting balance, real MT5 demo history, real signal_engine/risk_engine — same approach validated in prior iterations.

**Baseline (current live config) — combined both pairs:**
Net P&L $1,490.01 over 190 trading days. Avg daily P&L **$7.84** (0.78%/day), median $4.84. Days hitting the $100 target: **15/190 (7.9%)**. Days positive: 53.2%. Daily P&L std dev $60.42 (i.e. day-to-day noise is ~8x the average — the account has no reliable daily floor). Best day +$233.15, worst day **-$155.58**. Max losing-day streak: 8 days. Per-pair: EURUSD net $768.84 (189 days, only 1 day hit target), GBPUSD net $721.17 (190 days, only 1 day hit target) — the combined number benefits from diversification across the two pairs' independent daily variance, not from either pair individually being close to the target.

**Comparison run (2x risk-per-trade, 1%/2%/3% tiers, illustrative only — not shipped):** avg daily P&L roughly doubled to $12.38/day, days hitting target rose to 27/190 (14.2%) — still missing 6 days out of 7 — while max drawdown jumped from 21-25% to 34-35% and the worst single day worsened to -$245.86. Win rate and profit factor were unchanged (58%, ~1.14) — doubling risk didn't create more edge, it just scaled the same edge's good days and bad days up together, which is exactly what leverage does and does not fix a low expected-value-per-day problem.

**Verdict reported to user**: $100/day as a **minimum** (a guaranteed daily floor) is not achievable at any risk level — day-to-day variance ($60-85 std dev) exceeds the target itself, so a hard floor is a mathematical impossibility for a probabilistic strategy, not a tuning problem. As an **average** target, 10%/day would require roughly 12-13x the current risk-per-trade, which extrapolates to a mathematically guaranteed account blowup (drawdown scales roughly linearly with risk multiplier; 2x risk already pushed drawdown to 34-35%, so ~12x would exceed 100%). The realistic sustainable average at current minimized risk is **~$5-8/day (0.5-0.8%/day)** combined across both pairs, hitting the $100 mark on roughly 1 day in 12-13, with the possibility of a materially better realistic ceiling (~$10-15/day, ~1 day in 7 hitting target) only by accepting meaningfully higher drawdown risk (34%+) — recommended against, consistent with the "keep losses minimized" constraint.

---

## 2026-09-13 17:43:13 — Re-ran feasibility analysis at a smaller $15-20/day target

User asked to re-run the same analysis at a smaller, more plausible daily target ($15-20/day) instead of $100/day.

**Code change** (`backtesting/replay_backtest.py`, `main.py` — still the only files touched): generalized `--daily-target` to accept a comma-separated list (e.g. `"15,20,100"`) and refactored `_daily_metrics()` to evaluate all requested thresholds from the **same simulated trade sequence in one pass**, rather than re-running the full (multi-minute) 270-day/2-pair simulation once per threshold — the trade sequence itself doesn't depend on which $ threshold it's later compared against, so this avoids wasted recomputation while keeping the exact same, already-validated simulation logic.

**Re-ran both the baseline (current live config) and the earlier 2x risk-per-trade comparison**, same 270-day window, $1,000 balance, now evaluated at $15/$20/$100 simultaneously:

| | Baseline (0.5/1/1.5% risk) | 2x risk (1/2/3%, illustrative only) |
|---|---|---|
| Days hitting $15/day (combined) | 78/190 (41.1%) | 84/190 (44.2%) |
| Days hitting $20/day (combined) | 73/190 (38.4%) | 78/190 (41.1%) |
| Days hitting $100/day (combined) | 15/190 (7.9%) | 27/190 (14.2%) |
| Avg daily P&L (combined) | $7.85 | $12.34 |
| Median daily P&L (combined) | $4.84 | $6.61 |
| Worst day | -$155.58 | -$245.86 |
| Max drawdown (per pair) | 20.9-24.9% | 33.8-34.9% |

**Key finding**: $15-20/day is meaningfully more attainable than $100/day (hit ~4 days in 10 vs ~1 day in 12-13 at baseline risk) but still **not a reliable minimum** — median daily P&L ($4.84) is below both thresholds, meaning the typical day still falls short; it's achieved only on above-median days. A second, less obvious finding: doubling risk barely moved the $15/$20 hit-rate (38-41% → 41-44%, only +3pp) while nearly doubling the $100 hit-rate (7.9%→14.2%) and significantly worsening drawdown (21-25%→34-35%) — because $15-20 is already within baseline day-to-day variance, so more risk mostly inflates the tails (better best-days, worse worst-days) rather than lifting the typical day. For a target in this range, increasing risk is a poor trade: little consistency gained for a lot of added drawdown risk.

**No config changes shipped** — same as the $100/day analysis, this stays a reporting exercise; live risk-per-trade tiers remain at 0.5%/1.0%/1.5%.

---

## 2026-09-13 19:35:17 — $15-20-30/day iteration campaign: backtester fidelity overhaul + parameter sweep

User asked to actively iterate on parameters (risk, sizing, frequency, entry/exit rules, filters) toward a $15-$20-$30/day target, backtesting after each change, and to bring in news/sentiment analysis if price-action tuning alone wasn't enough.

**Critical discovery before any parameter tuning could be trusted**: the backtester (`backtesting/replay_backtest.py`) had several real fidelity gaps that made ALL of this session's earlier $100/day and $15-20/day reports optimistic:
1. SL/TP used a hardcoded `sl_mult=1.8, tp_mult=3.0` instead of calling the real, confidence/session-tiered `risk_engine.calculate_sl_tp()` — meaning the backtest never actually exercised the live TP-scaling logic it claimed to test.
2. No cooldown or `max_trades_per_day` enforcement at all — the backtest could take trades back-to-back that live trading's `risk_engine.can_take_trade()` would have blocked.
3. **Each pair was backtested against its own independent $1,000 balance and the results summed** — this effectively simulated **$1,000 per pair ($2,000 total)**, not one shared $1,000 account. Position sizing for GBPUSD never reflected EURUSD's concurrent drawdown or vice versa, which a real shared-balance account would.
4. The live news-event filter (`news_filter.is_safe_to_trade()`, already active as Gate 4 in `trading_orchestrator.py` for every live trade) was never modeled in the backtest at all.

**Rewrote `backtesting/replay_backtest.py`** to fix all four: real `calculate_sl_tp()` calls, per-pair cooldown + shared daily-trade-cap enforcement, a new `run_combined()` mode that simulates all pairs together on one shared, compounding account balance (the faithful "does the account hit $X/day" view — `run()` is kept for isolated single-pair diagnostics only), and a network-free recurring-major-event blackout filter (`--avoid-news`, mirroring `news_filter.py`'s own NFP/CPI/Fed/ECB/BOE fallback schedule, since no historical point-in-time economic-calendar dataset is available offline for exact-date accuracy). Also generalized `--daily-target` to accept multiple thresholds and added `--min-confidence`, `--cooldown-mult`, `--max-trades-per-day`, `--fixed-lot` as CLI-tunable levers for exactly this kind of experiment, all in-process only (never writing to `config.json`). `main.py`'s `run_backtest()` wrapper updated to forward all new flags.

**Iteration log** (all runs: 270 days ending "now", $1,000 shared balance, EUR/USD+GBP/USD combined, identical window across every experiment — no cherry-picking):

| # | Change | Trades | Net P&L | Profit Factor | Max DD | Avg daily P&L | $30/day hit rate | Verdict |
|---|---|---|---|---|---|---|---|---|
| E0 | Baseline (current live config, fidelity-fixed) | 406 | $288.14 | 1.09 | 18.4% | $1.57 | 22.3% | reference |
| E1 | Cooldown halved (more frequency) | 408 | $348.75 | 1.11 | 17.3% | $1.90 | 22.8% | no real effect — cooldown wasn't binding (only 40/14,239 signals blocked by it at baseline) |
| E2 | Confidence threshold 75→65 (more frequency) | 717 | $12.19 | 1.00 | 30.2% | $0.07 | 12.8% | **harmful** — 76% more trades but EURUSD flipped net-negative (-$138), drawdown nearly doubled |
| E4 | Fixed 0.1 lot (replacing dynamic sizing) | 405 | $246.25 | 1.09 | 25.5% | $1.34 | 16.8% | **worse than dynamic sizing** on both profit and drawdown — loses the confidence-based risk scaling |
| E5 | Avoid recurring high-impact news windows | 296 | $637.64 | 1.29 | 17.2% | $3.86 | 22.4% | **best single lever** — fewer, higher-quality trades; net profit +121% vs baseline |
| E6 | E5 + cooldown halved | 297 | $622.79 | 1.28 | 17.3% | $3.77 | 21.8% | identical to E5 — confirms cooldown is redundant even combined with news avoidance |
| E7 | E5 + 1.5x risk-per-trade (illustrative only) | 296 | $771.20 | 1.26 | 24.6% | $4.67 | 25.5% | real but costly tradeoff — +21% avg daily return for +7.4pp drawdown; not recommended |

**Important correction to earlier reports in this conversation**: E5 (avoid-news) is not a new feature — `trading_orchestrator.py` already gates every live trade through `news_filter.is_safe_to_trade()` (confirmed by re-reading the code). The live bot has always had this protection; the backtest simply never modeled it. This means E0's $1.57/day baseline understates what the live bot's news-blind trading would look like, while E5's $3.86/day is the more honest estimate of the **current, unchanged, already-deployed bot's** real expected performance — the earlier $100/day analysis's reported $7.84/day baseline figure should be considered superseded by this more faithful backtest; the gap is attributable to the four fidelity fixes above (shared-balance sizing being the largest single factor), not a real change in the bot's behavior.

**On sentiment analysis**: `news_engine/news_sentiment.py` (Finnhub headline scoring) already exists and feeds the live LLM decision path, but requires live, point-in-time news headlines with no historical archive available offline — it cannot be honestly backtested without a paid historical news dataset, so no retroactive validation of its impact is possible; its real effect can only be observed by watching live/demo trading going forward. The recurring-economic-calendar blackout (E5) was used instead as the feasible, honest "news-impact" lever, since it depends only on a fixed, publicly-known event schedule rather than fetched historical content.

**No config.json changes shipped.** None of the tested parameter changes (cooldown, confidence threshold, fixed lot sizing) improved on the current live configuration — several made it meaningfully worse. The one validated improvement (news avoidance) requires no code change since it's already live. The 1.5x risk option (E7) is reported as an available, quantified tradeoff, not adopted, per the explicit "keep losses minimized" constraint.

**Final verdict**: at the corrected, faithful baseline reflecting the bot's actual current configuration (E5), the account hits $15/day on 33.3% of days, $20/day on 27.3%, $30/day on 22.4% — a real, meaningful improvement in average return (more than doubled vs. the un-modeled-news-filter comparison) but still not a "consistent" or "minimum" outcome for any of the three thresholds; more than 2 in 3 days fall short of $15, and roughly 3 in 4 fall short of $30. Average daily P&L is $3.86 (0.39%/day); median is $1.61, confirming the "typical" day undershoots all three targets and the average is pulled up by a right tail of strong days. Worst day: -$46.34; max losing-day streak: 6 days.

---
