# ForexAI Trader — Complete Deployment Guide

## Table of Contents
1. System Architecture Overview
2. AI Decision Philosophy
3. Indicator Justification
4. Local Development Setup
5. VPS Production Deployment
6. TradingView Configuration
7. MT5 Configuration
8. Docker Deployment
9. Security Best Practices
10. Monitoring & Alerting
11. Performance Optimization
12. Future Scalability

---

## 1. System Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│                    SIGNAL SOURCES                          │
│  TradingView Alerts  │  Autonomous Scanner                 │
└──────────┬──────────┘            │                         │
           │                       │                         │
           ▼                       ▼                         │
┌─────────────────────────────────────────────┐             │
│           FASTAPI WEBHOOK SERVER            │             │
│  • Token validation  • Deduplication        │             │
│  • Rate limiting     • Stale check          │             │
└────────────────────┬────────────────────────┘             │
                     │                                       │
                     ▼                                       │
┌─────────────────────────────────────────────┐             │
│          TRADING ORCHESTRATOR               │             │
│                                             │             │
│  1. Kill Switch Check                       │             │
│  2. Session Filter (London/NY)              │             │
│  3. Risk Pre-Check (drawdown, limits)       │             │
│  4. News Filter (FF Calendar)               │             │
│  5. Spread Check                            │             │
│  6. MT5 Data Fetch (M15/H1/H4/D1)          │             │
│  7. Multi-Timeframe Analysis                │             │
│  8. Confidence Scoring (deterministic)      │             │
│  9. AI Decision (LLM if marginal)           │             │
│  10. RR Validation                          │             │
│  11. Position Sizing                        │             │
│  12. Trade Execution                        │             │
└────────────────────┬────────────────────────┘             │
                     │                                       │
                     ▼                                       │
┌─────────────────────────────────────────────┐             │
│          MT5 EXECUTION ENGINE               │             │
│  • Market orders with retry logic           │             │
│  • Requote handling                         │             │
│  • Slippage control                         │             │
└────────────────────┬────────────────────────┘             │
                     │                                       │
          ┌──────────┘                                       │
          ▼                                                   │
┌─────────────────────────────────────────────┐             │
│          TRADE MONITOR (background)         │             │
│  • Break-even movement                      │             │
│  • Trailing stop loss                       │             │
│  • Partial profit booking                   │             │
│  • Time-based exits                         │             │
│  • News emergency exit                      │             │
└────────────────────┬────────────────────────┘             │
                     │                                       │
                     ▼                                       │
┌─────────────────────────────────────────────┐             │
│              STORAGE (JSON/CSV)             │             │
│  active_trades.json  •  trade_history.csv   │             │
│  daily_stats.json    •  ai_logs.json        │             │
└────────────────────┬────────────────────────┘             │
                     │                                       │
                     ▼                                       │
┌─────────────────────────────────────────────┐             │
│         STREAMLIT DASHBOARD                 │             │
│  • Live positions • Equity curve            │             │
│  • P&L stats     • AI decisions             │             │
│  • Session info  • News risk                │             │
└─────────────────────────────────────────────┘             │
```

---

## 2. AI Decision Philosophy

### When AI (LLM) IS Used
| Condition | Reason |
|-----------|--------|
| Score 55–75 (marginal zone) | Human-like discretion needed |
| News risk: MEDIUM or HIGH | Fundamental context interpretation |
| MTF alignment < 75% | Regime ambiguity |
| Conflicting indicators | Complex confluence assessment |

### When AI is NOT Used (deterministic only)
| Condition | Reason |
|-----------|--------|
| Score ≥ 80 | Clear signal — no ambiguity |
| Score < 50 | Clear skip — LLM won't save it |
| No news events | Simple technical setup |
| Clean trend (all TFs aligned) | Algorithmic logic sufficient |

### Anti-Hallucination Measures
- Temperature = 0.1 (near-deterministic)
- Constrained JSON output (no free-form text)
- LLM adjustment bounded to ±15 points (max)
- Cache results for 15 minutes per pair
- Fallback to deterministic if LLM fails
- Validated response structure before use

### Model Selection
| Provider | Model | Use Case |
|----------|-------|----------|
| Anthropic Claude | claude-sonnet-4-20250514 | Primary (best reasoning) |
| OpenAI | gpt-4o-mini | Alternative (faster, cheaper) |
| Local (Ollama) | llama3.1:8b | Offline/VPS without internet |

---

## 3. Indicator Justification

### EMA Stack (9/21/50/200)
- **Purpose**: Trend direction at multiple speeds
- **Scientific basis**: Exponential weighting gives recent price more weight
- **Why 9/21/50**: Industry standard for short/medium/swing confirmation
- **200 EMA**: Institutional trend filter — price above = bullish regime
- **Weakness**: Lags in fast markets; use ATR to avoid whipsaws

### RSI (14)
- **Purpose**: Momentum + overbought/oversold detection
- **Use here**: Filter entries (don't buy overbought, don't sell oversold)
- **Not used**: As standalone signal (too many false reversals in trending markets)
- **Scientific basis**: 14-period is standard; works across all timeframes

### MACD (12/26/9)
- **Purpose**: Momentum direction + histogram for acceleration
- **Use here**: Confirmation only; histogram cross gives early signal
- **Weakness**: Lagging; don't use in choppy markets

### ATR (14)
- **Purpose**: Dynamic SL/TP sizing based on current volatility
- **Critical for**: Avoiding fixed pip SL that gets hit by normal price noise
- **Optimal ATR**: 12–40 pips on M15 for major pairs

### ADX (14)
- **Purpose**: Trend strength measurement (not direction)
- **Rules**: ADX < 20 = skip (no trend); 20–25 = emerging; > 25 = trending; > 40 = strong
- **Critical gate**: Never trade when ADX < 20 (choppy, random)

### Supertrend (10/3)
- **Purpose**: Trend following with built-in SL proxy
- **Use here**: Primary trend direction confirmation + visual SL
- **Advantage**: Adapts to volatility via ATR; cleaner than pure EMA in ranging markets

### Bollinger Bands (20/2)
- **Purpose**: Volatility envelope + squeeze detection
- **Use here**: BB squeeze signals potential breakout; width measures volatility regime
- **Not used**: As entry signal alone (too many false breakouts)

---

## 4. Local Development Setup

### Prerequisites
- Python 3.11+
- Windows (for MT5) or Linux (for webhook/dashboard only)
- MetaTrader 5 installed with broker account

### Step-by-Step

```bash
# 1. Clone/extract project
cd forex_ai_trader

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 5. Edit config/config.json
# - Set MT5 login/password/server
# - Set webhook secret token
# - Configure lot size and risk %

# 6. Start webhook server
uvicorn tradingview_webhook.webhook_server:app --host 0.0.0.0 --port 8000 --reload

# 7. Start dashboard (new terminal)
streamlit run dashboard/app.py

# 8. Test with a sample signal
python utils/webhook_examples.py
```

---

## 5. VPS Production Deployment

### Recommended VPS Specifications

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 2 GB | 4–8 GB |
| Storage | 20 GB SSD | 50 GB SSD NVMe |
| Network | 100 Mbps | 1 Gbps |
| OS | Ubuntu 22.04 | Ubuntu 22.04 LTS |
| Location | Broker's datacenter | LD4 (London) or NY4 (NY) for low latency |

**Top VPS Providers for Forex:**
1. **Contabo** — Best price/performance (Frankfurt/US)
2. **DigitalOcean** — Reliable, good NY/London options
3. **Vultr** — Low latency, good uptime
4. **ForexVPS** — Specialized, low latency to brokers
5. **Windows Cloud VPS** (if running MT5 directly on VPS)

> ⚠️ **MT5 runs on Windows only.** On Linux VPS, either:
> - Use the autonomous scanner + webhook (no MT5 needed for signal generation)
> - Run MT5 on a separate Windows machine/VPS and connect via API
> - Use Wine (limited compatibility)

### Linux VPS Setup

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install Python 3.11
sudo apt install python3.11 python3.11-venv python3-pip -y

# 3. Install Nginx (reverse proxy)
sudo apt install nginx certbot python3-certbot-nginx -y

# 4. Clone project
git clone https://github.com/yourrepo/forex_ai_trader.git /opt/forexai
cd /opt/forexai

# 5. Setup virtualenv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 6. Configure .env
cp .env.example .env
nano .env

# 7. Install as systemd services (auto-restart on crash)
sudo cp deployment/forexai-webhook.service /etc/systemd/system/
sudo cp deployment/forexai-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable forexai-webhook forexai-dashboard
sudo systemctl start forexai-webhook forexai-dashboard

# 8. Setup SSL with Let's Encrypt
sudo certbot --nginx -d yourdomain.com
```

### Systemd Service Files

Create `/etc/systemd/system/forexai-webhook.service`:
```ini
[Unit]
Description=ForexAI Webhook Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/forexai
Environment=PYTHONPATH=/opt/forexai
ExecStart=/opt/forexai/venv/bin/uvicorn tradingview_webhook.webhook_server:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 6. TradingView Configuration

### Step 1: Add Indicator
1. Open TradingView chart (EURUSD, M15)
2. Pine Editor → New → Paste `pine_script/forexai_indicator.pine`
3. Click Add to Chart

### Step 2: Create Alerts
For each pair you want to trade:
1. Right-click chart → Add Alert
2. Condition: `ForexAI Signals` → `BUY Signal` fired
3. Actions: Webhook URL → `https://your-domain.com/webhook?token=YOUR_SECRET`
4. Message (paste JSON):
```json
{"symbol":"{{ticker}}","timeframe":"{{interval}}","signal":"BUY","confidence":75,"timestamp":"{{timenow}}"}
```
5. Expiry: Open-ended
6. Repeat: Every bar close

Create separate alerts for:
- BUY signal
- SELL signal  
- (Optional) CLOSE signal

### Step 3: Alert Webhook URL Format
```
https://your-domain.com:8000/webhook
Header: X-TV-Token: YOUR_SECRET_TOKEN
```

Or as query parameter:
```
https://your-domain.com:8000/webhook?token=YOUR_SECRET_TOKEN
```

---

## 7. MT5 Configuration

### Step 1: Enable Algo Trading
MT5 → Tools → Options → Expert Advisors:
- ✅ Allow algorithmic trading
- ✅ Allow DLL imports

### Step 2: Account Configuration
In `config/config.json`:
```json
"mt5": {
    "login": 12345678,
    "password": "your_password",
    "server": "Broker-Server",
    "path": "C:/Program Files/MetaTrader 5/terminal64.exe",
    "magic_number": 202401
}
```

### Step 3: Verify Connection
```python
from mt5_execution.mt5_engine import mt5_engine
mt5_engine.connect()
info = mt5_engine.get_account_info()
print(info)
```

---

## 8. Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f webhook
docker-compose logs -f dashboard

# Stop services
docker-compose down

# Update and restart
git pull
docker-compose build
docker-compose up -d
```

---

## 9. Security Best Practices

| Area | Recommendation |
|------|---------------|
| Webhook Token | Use 32+ character random string |
| SSL | Always use HTTPS in production |
| Firewall | Allow only ports 80, 443, 22; block 8000 directly |
| SSH | Use key-based auth, disable password login |
| .env | Never commit to git; use secrets manager in cloud |
| Kill Switch | Always test kill switch before going live |
| API Keys | Set spending limits on AI provider accounts |
| Backups | Daily backup of storage/ directory |

### Generate Strong Token
```python
import secrets
print(secrets.token_urlsafe(32))
# Output: xK8mN2pQ7vL9wR3tY5uZ0aB6cD4eF1gH
```

---

## 10. Monitoring & Alerting

### Health Check URL
```
GET https://your-domain.com/health
→ {"status": "ok", "kill_switch": false, ...}
```

### Uptime Monitoring
- **UptimeRobot** (free): Monitor `/health` endpoint
- **BetterStack**: Enhanced monitoring with on-call alerts

### Log Files
```
storage/logs/execution.log     → All trade events
storage/logs/errors.log        → Exceptions only
storage/logs/ai_decisions.log  → LLM reasoning log
storage/logs/trade_events.log  → Entry/exit events
```

### Daily Summary (add to cron)
```bash
# Every day at 23:50 UTC
50 23 * * * cd /opt/forexai && python utils/daily_summary.py >> /tmp/summary.log
```

---

## 11. Latency Optimization

### Network Latency
- **Priority**: VPS in same datacenter as broker (e.g., LD4 for London brokers)
- **Target**: < 5ms to MT5 server
- **Test**: `ping broker-server.com`

### Code Optimizations
- News calendar cached for 1 hour (no repeated HTTP requests)
- LLM responses cached 15 minutes per pair
- State manager uses in-memory dict + atomic writes
- Trade monitor runs every 30 seconds (configurable)
- Indicator calculations use pandas-ta (vectorized C)

### Reduce LLM Calls
- Set `llm_cache_minutes: 30` for more aggressive caching
- Disable LLM entirely: `"enabled": false` in ai_engine config
- This reduces latency from ~500ms to < 5ms for decisions

---

## 12. Future Scalability

### Phase 2 Upgrades
1. **Redis Cache**: Replace in-memory LLM cache for multi-instance deployments
2. **Portfolio Heat Map**: Real-time correlation matrix for all pairs
3. **Adaptive Lot Sizing**: Machine learning-based sizing based on streak
4. **CrewAI Agents**: Multi-agent system for parallel pair analysis
5. **Order Flow Data**: Add tick data analysis for institutional entry detection
6. **Social Sentiment**: Twitter/Reddit sentiment for extreme move detection
7. **Custom LLM**: Fine-tune smaller model on historical trade decisions
8. **PostgreSQL Migration**: When trade volume exceeds 10,000 trades/month
9. **React Dashboard**: Replace Streamlit with custom React + WebSocket dashboard
10. **Multi-Account**: Route signals to multiple MT5 accounts simultaneously

### Scaling Architecture
```
Load Balancer (Nginx)
    ├── Webhook Server Instance 1
    ├── Webhook Server Instance 2
    └── Webhook Server Instance 3
            │
    Shared Redis Cache
            │
    Shared Storage (NFS/S3)
```

---

## Quick Start Checklist

```
□ Python 3.11+ installed
□ Virtual environment created and activated
□ pip install -r requirements.txt
□ .env configured (API keys, MT5 credentials, webhook secret)
□ config.json reviewed (lot size, risk %, pairs)
□ MT5 algorithmic trading enabled
□ MT5 connection tested (simulation mode first)
□ Webhook server running on port 8000
□ Dashboard accessible on port 8501
□ TradingView alerts configured with correct webhook URL
□ Kill switch tested
□ First trade in SIMULATION mode
□ SSL configured for production webhook
□ Daily backup script running
□ Health check monitoring active
```

---

*ForexAI Trader v1.0 — Trade smart, manage risk first.*
