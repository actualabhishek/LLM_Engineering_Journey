# Router Reachability Monitor

External reachability monitor for two internet edge routers (site LI-MDF). Pings both routers on an interval, runs an UP/DOWN state machine with debounce, sends multi-channel alerts (Telegram text, Telegram voice call, WhatsApp, ntfy), and serves a live NOC-style dashboard (green = UP, red = DOWN).

## Features

- ICMP + TCP probing with a canary check (1.1.1.1 / 8.8.8.8) so a local internet outage isn't mistaken for a router outage.
- Pure, unit-tested UP/DOWN state machine with configurable fail/recover thresholds and flap detection.
- Both routers down at once is treated as `SITE_ISOLATED` (critical severity, immediate voice call).
- Alerting via Telegram (text + inline ACK button + bot commands), CallMeBot voice call, WhatsApp, and ntfy — each channel independent, so one failing never blocks the others.
- Maintenance mode (mute a target for a time window) and a daily 09:00 IST summary.
- Dead-man's switch via healthchecks.io so the monitor is alerted if it stops running.
- Live dashboard over WebSocket (polling fallback), dark theme, Chart.js history graphs.
- SQLite storage, single Docker image (multi-arch: amd64 + arm64), deployed behind Tailscale Funnel (HTTPS) with no ports exposed on the host.

## Stack

Python 3.11+, asyncio, FastAPI + Uvicorn, WebSocket, SQLite (`aiosqlite`), `icmplib`, `httpx`, `pydantic-settings`, Jinja2 + vanilla JS + Chart.js. Tests: pytest + pytest-asyncio.

## Running locally

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp .env.example .env                                 # then fill secrets
uvicorn app.main:app --host 0.0.0.0 --port 8080
pytest -q
```

## Design notes

See `PLAN.md` for the full design and `CLAUDE.md` for the build/testing discipline followed throughout — every phase was proven with a real command and its output, logged in `docs/progress.md`.

---

Part of the `llm-engineering-journey` portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.
