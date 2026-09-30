# CLAUDE.md

Guidance for Claude Code when working in this repository. Read `PLAN.md` first for the full design; this file holds the rules.

## Project

External reachability monitor for two internet edge routers (site LI-MDF):

- `rtr01` LI-MDF-IRTR-1001-01, 32.142.239.74
- `rtr02` LI-MDF-IRTR-1001-02, 32.132.149.134

It pings on an interval, runs an UP/DOWN state machine with debounce, sends alerts (Telegram text, Telegram voice call via CallMeBot, WhatsApp via CallMeBot, ntfy), and serves a live dashboard (green = UP, red = DOWN). Everything must stay on free services.

Owner is a senior network engineer. Use networking terms freely (IP SLA, track, CoPP, BFD, flap) and explain new software concepts with networking analogies.

## Stack

Python 3.11+, asyncio, FastAPI + Uvicorn, WebSocket, SQLite (`aiosqlite`), `icmplib` (fallback: system `ping`), `httpx`, `pydantic-settings`, Jinja2 + vanilla JS + Chart.js. Tests: pytest + pytest-asyncio. Shipped as **one Docker container**, deployed on an Oracle Cloud Always Free Ubuntu VM, dashboard published over HTTPS with Tailscale Funnel (see `PLAN.md` section 12).

Do not target Vercel or any serverless/sleeping platform: the probe loop must run continuously and needs real ICMP and a persistent disk.

Do not add: a second container or sidecar, a separate database server, Redis/queues, a JS build toolchain (React/Vite/npm), or any paid API. Ask before adding a new dependency.

## Commands

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows (host OS)
pip install -r requirements.txt
cp .env.example .env                                 # then fill secrets
uvicorn app.main:app --host 0.0.0.0 --port 8080      # run monitor + dashboard
python scripts/test_alerts.py                        # send a test on every channel
pytest -q                                            # run tests
docker compose up -d --build                         # containerised run (local or VM)

# On the OCI VM
git pull && docker compose up -d --build             # deploy / update
docker compose logs -f --tail 200                    # watch probes
curl -s localhost:8080/healthz                       # liveness
docker compose exec monitor python scripts/test_alerts.py
sudo tailscale funnel --bg 8080                      # publish dashboard (one time)
```

Update this section if commands change.

## Layout

```
app/main.py            FastAPI app; starts monitor loop on startup
app/config.py          loads config.yaml + .env
app/db.py              SQLite schema, queries, retention
app/monitor/prober.py  ICMP + TCP probes, canaries
app/monitor/state.py   state machine (pure logic, no I/O)
app/monitor/scheduler.py asyncio probe loop
app/alerts/            base.Notifier interface + one file per channel, manager.py = escalation/ACK
app/web/               routes, WebSocket, templates, static
tests/                 unit tests (state machine first)
docs/progress.md       step-by-step proof log (commands + real output)
```

## Core rules

1. **State logic is pure.** `state.py` takes probe results and returns transitions. No network, DB, or clock calls inside; inject time. This keeps it fully unit-testable with simulated outages.
2. **Never alert on a single failure.** DOWN only after `fail_threshold` consecutive failed cycles; UP only after `recover_threshold` successes. Thresholds come from config, never hard-coded.
3. **Canary check before router alerts.** If all canaries (1.1.1.1, 8.8.8.8) fail, the monitor itself is offline: freeze router state and do not send router DOWN alerts.
4. **Both routers DOWN = `SITE_ISOLATED`**, severity CRITICAL, immediate voice call.
5. **Notifiers are independent.** Each implements `Notifier.send(alert) -> bool`. One channel failing (CallMeBot timeout, etc.) must never block or crash the others or the probe loop. Wrap every send with timeout + try/except, log the failure, record it in the `alerts` table.
6. **The probe loop must never die.** Catch and log per-target exceptions; keep cycling. A crash here means silent monitoring, the worst failure mode.
7. **Heartbeat** to healthchecks.io every cycle (or every minute) so the owner is alerted if the process stops.
8. **Every alert includes:** hostname, IP, new state, timestamp in IST (Asia/Kolkata), last RTT/loss, and for recovery the outage duration. Keep messages short enough to read on a phone lock screen.
9. **Recovery alerts are mandatory** for every DOWN alert sent.
10. **Respect rate limits.** CallMeBot is free and rate limited: dedupe, honour `repeat_every_s`, never loop-call.

## Dashboard rules

- Green `#16a34a` = UP, red `#dc2626` = DOWN, amber `#f59e0b` = flapping/degraded, grey = maintenance/unknown.
- Colour is never the only signal: always show the text UP/DOWN and an icon.
- Live updates over WebSocket; fall back to polling `/api/status` every 5s if the socket drops, and show a "connection lost" banner.
- Dark NOC theme, responsive (usable on phone), no external CDN required at runtime if possible (vendor Chart.js into `static/`).
- Times in IST.

## Deployment rules

- One image, one container (`monitor`) runs probe loop + alerts + dashboard. Same image for local and cloud.
- Dockerfile: `python:3.12-slim`, install `iputils-ping`, `sqlite3`, `tzdata`; run as non-root; `HEALTHCHECK` on `/healthz`; `CMD uvicorn app.main:app --host 0.0.0.0 --port 8080` with a single worker (the probe loop must not run twice).
- Compose: `restart: unless-stopped`, `cap_add: [NET_RAW]`, named volume at `/data`, `config.yaml` mounted read-only, `env_file: .env`, port published as `127.0.0.1:8080:8080` only, log rotation.
- The app must start cleanly on an empty `/data` (create schema on startup) and handle SIGTERM gracefully (finish current cycle, close DB).
- The image must build on both amd64 and arm64 (OCI A1 is ARM). No arch-specific wheels or binaries.
- Public exposure is only through Tailscale Funnel (HTTPS). Never publish the container port on `0.0.0.0` on the VM, and never open 80/443 in the OCI security list.
- Keep deployment steps in `PLAN.md` section 12.5 accurate; if you change how it deploys, update the runbook in the same change.

## Security and secrets

- Secrets live only in `.env`. Commit `.env.example` with empty values.
- `.gitignore` must include `.env`, `*.db`, `config.yaml` (commit `config.example.yaml`; real customer IPs stay out of public git).
- The dashboard is internet-facing: login is mandatory for every page, API and WebSocket (except `/healthz`). Credentials from `.env`. Rate-limit login attempts.
- Never log bot tokens, API keys, or full phone numbers.

## Code style: keep it simple

- **Simple, readable code first.** Write it so a network engineer new to Python can follow it. Plain functions and small classes, clear names, short comments where the "why" is not obvious.
- **Never over-engineer.** No extra abstraction layers, factories, plugin systems, metaclasses, or generic frameworks "for later". No features beyond `PLAN.md`. If two ways work, pick the one with less code.
- **No unnecessary defensive programming.** Handle the errors that can really happen (network timeouts, a notifier failing, bad config at startup). Do not wrap everything in try/except or add checks for impossible cases.
- Prefer the standard library; ask before adding a dependency.
- Type hints on function signatures, `async` for I/O, `logging` (not print) with one-line messages.
- Small modules, functions under ~40 lines where reasonable.
- Config values accessed through the settings object, not `os.environ` scattered in code.
- Store timestamps as UTC epoch seconds in the DB; convert to IST only for display and messages.

## Testing

- Unit test the state machine with a fake prober: normal, single drop, sustained outage, recovery, flapping, canary failure, both-down.
- Test the alert manager with fake notifiers (escalation timing, ACK stops repeats, one channel failing does not stop others).
- For end-to-end tests use `192.0.2.1` (TEST-NET-1, never replies) as a target. Do not generate artificial load against the real routers; keep probe rate as configured.

## Prove it works: test after every step

- Build in the phase order from `PLAN.md` section 11, one small step at a time.
- **After every step, test it and prove it works before moving to the next step.** Proof means running the real command (pytest, a curl, a probe run, a test alert) and showing its actual output. Never claim something works without running it.
- Record the proof in `docs/progress.md` for each step: what was built, the exact command(s) run, and the real output (trimmed if long). Never write output you did not see.
- If a step's test fails, stop and fix it. Do not start the next step on top of a broken one.
- A phase is closed only when its "Done when" check in `PLAN.md` section 11 passes and is recorded.
- Run the full `pytest -q` before closing each phase so earlier steps are not broken.

## Debugging: prove broken, fix, prove fixed

Like a network troubleshooting ticket: capture the evidence, change one thing, verify with the same test.

1. **Prove what is broken first.** Reproduce the problem with a failing test or a command, and show the real error/output. Do not guess and patch.
2. **Find the cause** from the evidence (logs, output, traceback). State it in one or two lines.
3. **Apply the smallest fix** that addresses that cause. One change at a time.
4. **Prove it is fixed** by running the exact same test or command again and showing it now passes.
5. Where it makes sense, keep the failing test as a regression test.
6. Log the bug in `docs/progress.md`: symptom, proof of failure, cause, fix, proof of fix.

## Workflow
- Keep `PLAN.md` in sync when design decisions change.
- The README (when written) ends with this exact line:
  "Part of the `llm-engineering-journey` portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering."
