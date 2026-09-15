# ForexAI Trader

**An autonomous forex trading system for MT5, built from the ground up — and from 16 years of watching networks fail in every way networks can fail.**

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [Configuration](#configuration)
5. [Running the System](#running-the-system)
6. [TradingView Setup](#tradingview-setup)
7. [MT5 Setup](#mt5-setup)
8. [Dashboard](#dashboard)
9. [Backtesting](#backtesting)
10. [Deployment (VPS)](#deployment-vps)
11. [Docker Deployment](#docker-deployment)
12. [Tests](#tests)
13. [Security](#security)
14. [Module Reference](#module-reference)
15. [Philosophy & Design Decisions](#philosophy--design-decisions)
16. [Roadmap](#roadmap)

---

## Overview

I spent 16 years keeping enterprise networks up — F5 load balancers, Cisco ISE, Nexus fabrics, the kind of infrastructure where a bad decision at 2 AM costs someone real money. This project is where that instinct meets my AI/ML transition: a trading system built the way I'd want a trading system built, if I were the one whose capital was on the line. Which I am.

ForexAI Trader is hands-on, still-evolving, and grounded in real backtests rather than backtest marketing. Here's what it actually does:

- Trades forex pairs on the M15 timeframe
- Combines deterministic technical analysis with selective LLM reasoning — the AI only steps in when the signal is genuinely ambiguous
- Executes, monitors, and manages trades via the MetaTrader 5 Python API
- Receives signals from TradingView webhooks
- Filters trades around high-impact news events
- Protects capital via multi-layer risk management
- Displays live metrics on a Streamlit dashboard

### Currently Traded Pairs
`EURUSD` · `GBPUSD`

I started wider and narrowed it down on purpose — more on why in [Philosophy & Design Decisions](#philosophy--design-decisions). The engine supports more pairs; I'm just not trading them yet, because the backtests didn't earn it. (`AUDUSD`, `USDCAD`, `EURJPY`, `GBPJPY` are wired up but dormant — see `config/config.json`.)

---

## Architecture

```
forex_ai_trader/
├── main.py                         # Entry point
├── trading_orchestrator.py         # Master pipeline coordinator
│
├── core/
│   ├── config_manager.py           # Singleton config loader
│   ├── logger.py                   # Structured logging (4 log files)
│   ├── session_manager.py          # London/NY/Overlap/Asian detection
│   └── state_manager.py            # Atomic JSON state + kill switch
│
├── strategies/
│   ├── indicators.py               # EMA/RSI/MACD/ATR/ADX/Supertrend
│   ├── multi_timeframe.py          # D1+H4+H1+M15 alignment scoring
│   └── confidence_engine.py        # 0-100 deterministic score + grade
│
├── ai_engine/
│   └── decision_engine.py          # Hybrid deterministic+LLM engine
│
├── risk_management/
│   └── risk_engine.py              # Pre-trade gate + SL/TP + trailing
│
├── mt5_execution/
│   ├── mt5_engine.py               # Full MT5 Python API integration
│   └── trade_monitor.py            # Background trade management daemon
│
├── tradingview_webhook/
│   └── webhook_server.py           # FastAPI + HMAC validation
│
├── news_engine/
│   └── news_filter.py              # Forex Factory calendar + risk levels
│
├── dashboard/
│   └── app.py                      # Streamlit live dashboard
│
├── backtesting/
│   └── backtest_engine.py          # Bar-by-bar + Monte Carlo simulation
│
├── utils/
│   ├── daily_summary.py            # EOD/weekly report generator
│   └── webhook_examples.py         # Example TV alert payloads
│
├── pine_script/
│   └── forexai_indicator.pine      # TradingView indicator + alerts
│
├── deployment/
│   ├── forex-ai-trader.service     # Systemd service (main system)
│   ├── forex-ai-webhook.service    # Systemd service (webhook only)
│   ├── forex-ai-dashboard.service  # Systemd service (dashboard)
│   └── nginx.conf                  # Nginx reverse proxy + SSL
│
├── config/
│   └── config.json                 # Master configuration
│
├── storage/
│   ├── active_trades.json          # Live trade state (atomic)
│   ├── trade_history.csv           # Closed trade log
│   ├── ai_logs.json                # AI decision ring buffer (100 entries)
│   ├── daily_stats.json            # Daily performance counters
│   └── logs/
│       ├── execution.log
│       ├── errors.log
│       ├── ai_decisions.log
│       ├── trade_events.log
│       └── daily_reports/          # Generated EOD text reports
│
├── tests/
│   ├── conftest.py
│   └── test_core_modules.py        # 30+ unit tests
│
├── .env.example                    # Environment variable template
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── DEPLOYMENT_GUIDE.md             # Detailed VPS/Docker guide
```

---

## Quick Start

### Prerequisites

| Requirement | Version |
|-------------|---------|
| Python      | ≥ 3.11  |
| MetaTrader 5 (Windows) | Any recent build |
| TradingView | Free or paid (for alerts) |
| VPS (optional) | Ubuntu 22.04 LTS recommended |

### 1. Clone and install

```bash
git clone https://github.com/youruser/forex_ai_trader.git
cd forex_ai_trader

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
nano .env                          # Fill in MT5 credentials, API keys
```

### 3. Run in simulation mode (no real trades)

```bash
python main.py --dry-run
```

### 4. Run in production

```bash
python main.py
```

---

## Configuration

Edit `config/config.json` to customise all trading parameters.

### Key settings

```json
{
  "pairs": ["EURUSD", "GBPUSD"],
  "timeframe": "M15",

  "risk": {
    "lot_size": 0.1,
    "max_risk_pct": 1.0,
    "max_concurrent_trades": 3,
    "max_daily_trades": 6,
    "max_daily_drawdown_pct": 3.0,
    "trade_cooldown_minutes": 30
  },

  "ai": {
    "use_llm": true,
    "llm_threshold_low": 55,
    "llm_threshold_high": 75,
    "cache_minutes": 15
  },

  "confidence": {
    "min_score_active_session": 65,
    "min_score_off_session": 80
  }
}
```

See `config/config.json` for the complete reference with all options documented inline.

---

## Running the System

```bash
# Full production system (all components)
python main.py

# Simulation mode — no real MT5 orders
python main.py --dry-run

# Override which pairs to trade
python main.py --pairs EURUSD GBPUSD

# Webhook server only (test TradingView alerts)
python main.py --mode webhook

# Backtester
python main.py --mode backtest

# Streamlit dashboard
python main.py --mode dashboard

# Use alternate config
python main.py --config /path/to/other_config.json
```

---

## TradingView Setup

### 1. Add the indicator

1. Open TradingView → Pine Script Editor
2. Paste contents of `pine_script/forexai_indicator.pine`
3. Click **Add to chart**

### 2. Create an alert

1. Right-click any signal label → **Create alert**
2. Set condition: **ForexAI — BUY Signal** (or SELL)
3. Under **Notifications** → enable **Webhook URL**
4. Enter your webhook URL:
   ```
   https://your-domain.com/webhook
   ```
5. Set the **Message** to the Pine Script alert message (it auto-fills with JSON)

### 3. Webhook payload format

```json
{
  "symbol":     "EURUSD",
  "timeframe":  "M15",
  "action":     "BUY",
  "confidence": 78,
  "sl":         1.07500,
  "tp":         1.08700,
  "atr":        0.00120,
  "spread":     0.6,
  "trend":      "up",
  "timestamp":  "{{timenow}}",
  "token":      "YOUR_WEBHOOK_TOKEN"
}
```

---

## MT5 Setup

### Environment variables (in `.env`)

```env
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=YourBroker-Live
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
```

### Notes

- MT5 must run **on the same Windows machine** (or Windows VM/Wine) as the Python backend.
- The system auto-reconnects up to 5 times if MT5 disconnects.
- With `--dry-run`, all MT5 calls are simulated locally.
- Symbol names may differ by broker (e.g. `EURUSDm` instead of `EURUSD`) — set `symbol_suffix` in config.

---

## Dashboard

Launch with:

```bash
python main.py --mode dashboard
# or directly:
streamlit run dashboard/app.py
```

Open `http://localhost:8501` in your browser.

### Dashboard panels

| Panel | Content |
|-------|---------|
| Live Positions | Symbol, direction, P&L, SL/TP, duration |
| Equity Curve | Rolling profit chart |
| Daily Stats | Win rate, profit factor, drawdown |
| AI Decisions | Last 20 AI decisions with confidence |
| Pair Performance | Per-pair win rate and net P&L |
| Session Status | Current session + news risk |

---

## Backtesting

```bash
python main.py --mode backtest
```

Or run directly:

```bash
python backtesting/backtest_engine.py
```

### Output metrics

- Win rate / Loss rate
- Profit factor
- Sharpe ratio / Sortino ratio
- Maximum drawdown
- Expectancy per trade
- Session-breakdown performance
- Monte Carlo (1000 simulations) — best/worst/median equity

Reports are saved to `storage/logs/daily_reports/`.

I lean on this harder than any single indicator. Backtesting is what told me gold wasn't ready — see [Philosophy & Design Decisions](#philosophy--design-decisions) for that story.

---

## Deployment (VPS)

### Recommended VPS specs

| Tier | CPU | RAM | Storage | Location |
|------|-----|-----|---------|----------|
| Minimum | 2 vCPU | 2 GB | 20 GB SSD | LD4 or NY4 |
| Recommended | 4 vCPU | 4–8 GB | 40 GB SSD | LD4 or NY4 |

Low-latency VPS providers: **Contabo**, **Vultr**, **Hetzner**, **DigitalOcean**

### Install on Ubuntu 22.04

```bash
# 1. Create a dedicated user
sudo useradd -m -s /bin/bash forexai
sudo su - forexai

# 2. Clone and install
git clone https://github.com/youruser/forex_ai_trader.git /opt/forex_ai_trader
cd /opt/forex_ai_trader
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Copy env file
cp .env.example .env
nano .env   # fill in credentials

# 4. Install systemd services
sudo cp deployment/forex-ai-trader.service    /etc/systemd/system/
sudo cp deployment/forex-ai-webhook.service   /etc/systemd/system/
sudo cp deployment/forex-ai-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now forex-ai-trader
sudo systemctl enable --now forex-ai-dashboard

# 5. Install Nginx + SSL
sudo apt install nginx certbot python3-certbot-nginx -y
sudo cp deployment/nginx.conf /etc/nginx/sites-available/forex-ai-trader
# Edit nginx.conf: replace your-domain.com with your actual domain
sudo ln -s /etc/nginx/sites-available/forex-ai-trader /etc/nginx/sites-enabled/
sudo certbot --nginx -d your-domain.com
sudo systemctl reload nginx
```

### Service management

```bash
sudo systemctl status  forex-ai-trader
sudo systemctl restart forex-ai-trader
sudo journalctl -u forex-ai-trader -f   # follow logs
```

---

## Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

Services started:
- `webhook` — FastAPI on port 8000
- `dashboard` — Streamlit on port 8501

---

## Tests

```bash
# Install test dependencies
pip install pytest

# Run all tests
pytest tests/ -v

# Run specific test class
pytest tests/test_core_modules.py::TestConfidenceEngine -v

# With coverage
pip install pytest-cov
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## Security

| Feature | Implementation |
|---------|---------------|
| Webhook authentication | HMAC-SHA256 token in every alert |
| Rate limiting | 10 requests/min per pair (FastAPI) |
| Duplicate prevention | MD5 hash deduplication (60 s window) |
| Kill switch | HTTP endpoint + state file |
| SSL/TLS | Nginx + Let's Encrypt |
| Dashboard auth | Nginx basic auth + IP allowlist |
| API keys | `.env` file, never in source |
| Kill switch IP restriction | Nginx `allow`/`deny` directives |

**Never commit your `.env` file.** The `.gitignore` excludes it by default.

Sixteen years of enterprise networking left me with a low tolerance for "it'll probably be fine" security. Kill switch, rate limiting, IP allowlists — these aren't decoration.

---

## Module Reference

### `main.py`
Entry point. Parses CLI args, starts all components in order.
```
--mode  {full|webhook|backtest|dashboard}
--dry-run
--pairs EURUSD GBPUSD ...
--config /path/to/config.json
```

### `trading_orchestrator.py`
12-step pipeline per signal:
1. Validate signal → 2. Session check → 3. News check → 4. Fetch candles →
5. Compute indicators → 6. MTF alignment → 7. Confidence score →
8. AI decision → 9. Risk gate → 10. Compute SL/TP → 11. Execute →
12. Log everything

### `ai_engine/decision_engine.py`
Hybrid engine:
- **Score ≥ 80 or < 50** → pure deterministic (no LLM call)
- **Score 55–75** → LLM reasoning (Claude Sonnet, temperature 0.1)
- LLM adjustment capped at ±15 points
- 15-minute per-pair response cache
- Automatic fallback to deterministic on LLM failure

### `strategies/confidence_engine.py`
Scores 0–100 across 8 factors:

| Factor | Max Points |
|--------|-----------|
| MTF alignment | 25 |
| Momentum (RSI+MACD) | 20 |
| Session quality | 15 |
| Spread | 10 |
| Volatility (ATR) | 10 |
| Trend strength (ADX) | 10 |
| RSI position | 5 |
| Market structure | 5 |

News risk applies a penalty of 5–30 points.

### `risk_management/risk_engine.py`
Pre-trade checks (any failure = reject):
- Kill switch active?
- Daily drawdown exceeded?
- Max concurrent trades reached?
- Daily trade limit reached?
- Pair cooldown active?
- Duplicate trade on same pair?

SL/TP: ATR × multiplier, adjusted for spread cost.

### `news_engine/news_filter.py`
- Fetches Forex Factory calendar (1-hour cache)
- Risk levels: LOW / MEDIUM / HIGH / EXTREME
- Pause window: 30 min before → 15 min after event
- EXTREME events (NFP, FOMC): triggers close-all

### `utils/daily_summary.py`
Generates text reports with:
- Win rate, P&L, profit factor, expectancy
- By-pair and by-session breakdown
- AI engine usage stats
- Optional email (SMTP) and webhook delivery

---

## Philosophy & Design Decisions

I built this the way I'd audit a network — assume it'll break, find out how, before it costs anything real.

### Why not a database?
Trade execution speed is critical. JSON atomic writes (`rename()` trick) are sub-millisecond and never block execution. SQLite adds lock contention; PostgreSQL adds network round-trips. For the trade volumes this system handles (<10 trades/day), JSON + CSV is optimal. Simple, and I can debug it by opening a text file — that matters more than it sounds.

### Why selective LLM use?
- LLMs are slow (0.5–3 s latency) and costly
- Most forex decisions are rule-based and deterministic
- LLM adds value only in the **ambiguous regime** (score 55–75) — where a second opinion is actually worth the wait
- Caching eliminates redundant API calls for the same pair within 15 min
- Hard cap (±15 pts) prevents hallucination-driven outlier decisions

### Why M15 timeframe?
- Enough signal, not too much noise
- Respects spread cost at 0.1 lot (~$1 per trade)
- Aligns with London/NY institutional activity windows
- Confirmed by D1+H4+H1 multi-timeframe alignment before entry

### Why only two pairs right now?
I started broader — seven pairs, more surface area, more "coverage." Then I sat down with actual research on forex mechanics and looked hard at the live code with fresh eyes. EUR/USD and GBP/USD are simply the cleanest majors for 15-minute intraday trading: tightest spreads, deepest liquidity, the most honest event-driven moves. I narrowed to those two, added a strict same-day flat-close at 21:00 UTC, and moved to equity-based position sizing. The other pairs are still wired into the engine — dormant, not deleted — because "supports more pairs" and "should trade more pairs" are different claims, and I only want to make the second one when the numbers back it up.

That same discipline is why gold isn't on this list either. I ran a full 270-day backtest on XAUUSD out of curiosity, using the same methodology as the majors. Once I fixed a real bug in the pip-value math — gold doesn't fit the "JPY pairs vs. everything else" pip-size assumption the rest of the codebase leaned on — the honest result was a 127% max drawdown. Simulated account, fully blown up. The cause wasn't the strategy; it was structural: gold's dollar volatility is too large for a $1,000 account's minimum tradeable lot (0.01), so the risk engine's 1%-per-trade target kept getting overridden by a lot-size floor it couldn't size below. I kept the pip-value fix — it's correct and reusable — but gold stays out of `config.json` until the account size or the stop-loss model changes. Still learning where this system's edges actually are, one uncomfortable backtest at a time.

### Why no overtrading protection from indicators alone?
We rely on **session filters + news filters + cooldown + max daily trades** rather than indicator complexity. Keeping the indicator layer simple and fast lets the AI layer focus on genuine edge cases.

---

## Roadmap

### Phase 2 (Near-term)
- [ ] React + FastAPI dashboard (replaces Streamlit)
- [ ] Redis caching for AI decisions across multi-process deployments
- [ ] Telegram bot integration for trade alerts
- [ ] Walk-forward optimisation framework
- [ ] Order block + Fair Value Gap (FVG) detection

### Phase 3 (Advanced)
- [ ] Portfolio-level correlation management
- [ ] Local LLM option (Ollama + Mistral/Llama)
- [ ] Sentiment analysis via news headlines API
- [ ] Adaptive lot sizing based on rolling win rate
- [ ] Multi-broker failover (MT5 + cTrader)
- [ ] Hard risk-engine check: skip the trade if even the minimum lot exceeds acceptable risk (the gap the gold backtest surfaced)

---

## License

MIT — use freely, trade responsibly.

---

> ⚠️ **Disclaimer**: This software is for educational purposes. Forex trading carries significant risk. Past performance does not guarantee future results. Always test thoroughly in simulation before live trading.

---

16 years of networks, now speaking Python. Still learning, still building.

---

Part of the `llm-engineering-journey` portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.
