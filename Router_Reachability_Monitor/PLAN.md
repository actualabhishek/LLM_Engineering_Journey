# PLAN.md: Router Reachability Monitor

## 1. Goal

Continuously monitor external (internet) reachability of two edge routers, raise an alert the moment a node goes down, and show live status on a professional dashboard. Every component must be free to run.

| Hostname | Public IP | Role |
|---|---|---|
| LI-MDF-IRTR-1001-01 | 32.142.239.74 | Internet router 1 (MDF) |
| LI-MDF-IRTR-1001-02 | 32.132.149.134 | Internet router 2 (MDF) |

Both routers sit in the same MDF, so **both down at once = site isolated** and must be treated as a higher severity than a single router down.

---

## 2. Scope

### In scope (MVP)
1. ICMP ping probe on a fixed interval (default 10s) for each target.
2. UP/DOWN state machine with debounce (no alert on a single lost packet).
3. Alerts on DOWN and on RECOVERY via Telegram text, Telegram voice call, and WhatsApp.
4. Live web dashboard: green/red tiles, RTT, packet loss, last change, uptime %, event log.
5. History stored locally (SQLite) for graphs and uptime reports.

### Added items (not in original request, recommended)
1. **Secondary TCP probe** (e.g. TCP/22 or TCP/443 connect) so a router that deprioritises ICMP under CoPP load is not falsely marked down. Node is DOWN only when ICMP **and** TCP both fail (configurable).
2. **Monitor self-check (canary targets):** ping 1.1.1.1 and 8.8.8.8 every cycle. If the canaries also fail, the problem is *our* internet, not the routers. Suppress router alerts and send "Monitor lost internet" instead. Without this, every home broadband drop pages you twice.
3. **Dead-man's switch:** monitor sends a heartbeat to healthchecks.io (free tier). If the monitor process or PC dies, healthchecks.io alerts you on Telegram. Answers the question "who monitors the monitor?"
4. **Alert acknowledgement:** Telegram inline "ACK" button. Unacknowledged DOWN alerts repeat every N minutes and escalate to a voice call.
5. **Flap detection:** if a node changes state more than X times in Y minutes, send one "FLAPPING" alert instead of a storm.
6. **Maintenance mode:** mute alerts for a node for a time window (from dashboard or Telegram `/mute 01 60`).
7. **Telegram bot commands:** `/status`, `/mute`, `/unmute`, `/ack`, `/report`.
8. **Daily summary** at 09:00 IST: uptime %, outages, avg RTT, max loss for the last 24h.
9. **Latency degradation warning** (optional): alert when RTT or loss crosses a threshold for N cycles, before a hard down.

### Out of scope (for now)
SNMP polling, interface/BGP state, syslog, multi-site. Can be added later since the probe layer is pluggable.

---

## 3. Free alert channels (researched options)

| Channel | Tool | Cost | How it works | Notes |
|---|---|---|---|---|
| Telegram text | Telegram Bot API (@BotFather) | Free, unlimited | `sendMessage` to your chat ID | Primary channel. Reliable, supports buttons for ACK. |
| Telegram audio message | Bot API `sendVoice` + TTS (gTTS / edge-tts) | Free | Generate "Router 01 is down" as .ogg, send as voice note | Plays a voice note, but does **not** ring like a call. |
| **Telegram voice call** | CallMeBot Telegram Call API | Free (personal use) | HTTP GET, CallMeBot places a real Telegram call and reads text via TTS | Closest free option to a "phone call". One-time authorisation: message @CallMeBot_txtbot. Rate limited. |
| WhatsApp text | CallMeBot WhatsApp API | Free (personal use) | HTTP GET with phone + apikey | Get apikey by sending the activation message to CallMeBot's WhatsApp number. Rate limited, best-effort. |
| Push (backup) | ntfy.sh | Free | HTTP POST to a topic, Android/iOS app | Priority 5 bypasses Do Not Disturb. Good fallback if CallMeBot is slow. |
| Email (backup) | Gmail SMTP + App Password | Free | SMTP | Audit trail. |
| Real PSTN phone call | Twilio / Exotel | **Not free** (trial only) | | Keep as future paid option. Design the notifier interface so it can be added later. |

**Escalation policy (default):**

| Time since DOWN | Action |
|---|---|
| T+0 | Telegram text (with ACK button) + WhatsApp + ntfy |
| T+2 min, not ACKed | Telegram voice call via CallMeBot |
| Every 10 min, not ACKed | Repeat Telegram text + voice call |
| Recovery | Telegram + WhatsApp "RECOVERED, down for 7m 32s" |
| Both routers down | Immediate voice call (skip the 2 min wait), severity CRITICAL |

Note: CallMeBot is a free third-party service with no SLA. That is why Telegram Bot API is primary and CallMeBot is the "loud" layer on top. Verify current CallMeBot endpoints and limits at build time.

---

## 4. Architecture

Networking analogy: think of it as **IP SLA + track objects + EEM**. The prober is `ip sla icmp-echo`, the state engine is `track ... reachability` with `delay down/up`, and the alert manager is the EEM applet that fires on a track state change.

```
                +-----------------------------+
                |        config.yaml / .env   |
                +--------------+--------------+
                               |
+-------------+   results   +--v--------------+  state change  +------------------+
|  Prober     +------------>+  State Engine   +--------------->+  Alert Manager   |
| ICMP + TCP  |             | debounce, flap, |                | escalation, ACK, |
| + canaries  |             | maintenance     |                | dedupe, repeat   |
+------+------+             +--+-----------+--+                +---+----+----+----+
       |                       |           |                       |    |    |
       |                 +-----v----+  +---v--------------+   Telegram  |  CallMeBot
       +---------------->+ SQLite   |  | WebSocket push   |   Bot API   |  (call/WA)
                         | history  |  | to dashboard     |            ntfy / email
                         +-----+----+  +---+--------------+
                               |           |
                         +-----v-----------v-----+        +---------------------+
                         | FastAPI web server    |<------>| Browser dashboard   |
                         | REST + WebSocket      |        | green/red live view |
                         +-----------------------+        +---------------------+
                               |
                         heartbeat -> healthchecks.io (dead-man's switch)
```

Single Python process (asyncio). No external DB, no message broker. Packaged as **one Docker container**, deployed 24x7 on a free Oracle Cloud VM (see section 12). Also runs locally on Windows for development.

---

## 5. Tech stack (all free / open source)

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Matches existing projects |
| Probing | `icmplib` (async ICMP) with fallback to system `ping` | Async, gives RTT/loss/jitter. Fallback handles Windows privilege quirks. |
| TCP probe | `asyncio.open_connection` with timeout | No dependency |
| Scheduler | asyncio loop (no cron) | Sub-minute intervals |
| Web / API | FastAPI + Uvicorn | REST + WebSocket in one server |
| Dashboard UI | Jinja2 template + vanilla JS + Chart.js (or Apache ECharts) | No build step, loads fast, looks professional |
| Storage | SQLite (via `aiosqlite`) | Zero admin, file-based |
| Telegram | `httpx` calls to Bot API (or `python-telegram-bot` for commands/ACK) | |
| TTS | `edge-tts` or `gTTS` | Free voice note generation |
| Config | `config.yaml` + `.env` (secrets) via `pydantic-settings` | |
| Packaging | Single Docker container + docker compose | Same image in dev and prod |
| Hosting | Oracle Cloud Always Free VM (Ubuntu) | Always on, real ICMP, persistent disk, free |
| Public HTTPS | Tailscale Funnel | Free stable HTTPS URL, no open inbound ports |
| Tests | pytest + pytest-asyncio | |

---

## 6. Detection logic

Per target, every `interval` seconds:

1. Send `count=3` ICMP echoes, `timeout=1s` each. Record RTT min/avg/max, loss %, jitter.
2. If ICMP loss = 100% and TCP probe is enabled, try TCP connect to `tcp_port`.
3. Cycle result = `OK` if ICMP succeeded (or TCP succeeded), else `FAIL`.
4. Before evaluating router state, check canaries. If all canaries FAIL, mark monitor as `ISOLATED`, freeze router states, send one "Monitor lost internet" alert (through any channel still possible, and healthchecks.io will catch it too).
5. State machine:

```
UNKNOWN --(first result)--> UP or DOWN
UP   --(fail_threshold consecutive FAIL, default 3)--> DOWN     => alert DOWN
DOWN --(recover_threshold consecutive OK, default 2)--> UP      => alert RECOVERED
any  --(> flap_count changes in flap_window)--> FLAPPING        => one alert, suppress until stable
```

With interval 10s and fail_threshold 3, detection time is about 30 to 40 seconds. Tunable in config.

6. Site-level rule: if both routers DOWN, raise `SITE_ISOLATED` (CRITICAL).

---

## 7. Dashboard spec

Look: dark NOC style, clean, readable on a wall screen and on mobile.

- **Header:** site name, overall status banner (All UP = green, Degraded = amber, Site Isolated = red), monitor health (canary OK, last heartbeat), current time IST.
- **Node tiles (one per router):** large tile, **green = UP, red = DOWN** (pulsing red border on DOWN, amber for FLAPPING/degraded, grey for maintenance). Shows hostname, IP, current RTT, loss %, "UP for 3d 4h" or "DOWN for 5m 12s", last check time, 24h uptime %.
- **Live RTT chart:** last 1h line chart per router, updates every cycle via WebSocket.
- **Availability bar:** 24h/7d strip of green/red segments (status-page style).
- **Event log:** table of state changes, alert sent, ACK by, duration.
- **Controls:** Mute/maintenance toggle per node, "Send test alert" button.
- **Accessibility:** colour is not the only signal. Tiles also show text "UP"/"DOWN" and an icon.
- Optional: browser sound + tab title flashes "DOWN" when a node goes red.

API endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Dashboard page |
| GET | `/api/status` | Current state of all targets |
| GET | `/api/history?target=&range=1h` | RTT/loss series |
| GET | `/api/events?limit=100` | Event log |
| POST | `/api/targets/{id}/mute` | Maintenance mode |
| POST | `/api/alerts/test` | Test all channels |
| WS | `/ws` | Live push of results and state changes |
| GET | `/healthz` | Liveness |

---

## 8. Data model (SQLite)

```sql
targets(id TEXT PK, hostname TEXT, ip TEXT, tcp_port INT, enabled INT)
probe_results(ts INTEGER, target_id TEXT, ok INT, rtt_avg REAL, rtt_min REAL,
              rtt_max REAL, loss_pct REAL, jitter REAL, method TEXT)   -- index (target_id, ts)
state_events(id INTEGER PK, ts INTEGER, target_id TEXT, from_state TEXT,
             to_state TEXT, duration_s INTEGER, reason TEXT)
alerts(id INTEGER PK, ts INTEGER, event_id INT, channel TEXT, status TEXT,
       acked_by TEXT, acked_ts INTEGER, error TEXT)
maintenance(target_id TEXT, start_ts INTEGER, end_ts INTEGER, note TEXT)
```

Retention: raw `probe_results` 30 days (configurable), then roll up to 5-minute averages.

---

## 9. Configuration example

`config.yaml`
```yaml
site: "LI-MDF"
timezone: "Asia/Kolkata"
probe:
  interval_s: 10
  icmp_count: 3
  icmp_timeout_s: 1
  fail_threshold: 3
  recover_threshold: 2
  tcp_fallback: true
flap:
  max_changes: 4
  window_s: 600
canaries: ["1.1.1.1", "8.8.8.8"]
targets:
  - id: rtr01
    hostname: LI-MDF-IRTR-1001-01
    ip: 32.142.239.74
    tcp_port: 22
  - id: rtr02
    hostname: LI-MDF-IRTR-1001-02
    ip: 32.132.149.134
    tcp_port: 22
alerts:
  escalate_call_after_s: 120
  repeat_every_s: 600
  channels: [telegram, telegram_call, whatsapp, ntfy]
dashboard:
  host: 0.0.0.0
  port: 8080
```

`.env` (never committed)
```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
CALLMEBOT_TG_USER=@yourusername
CALLMEBOT_WA_PHONE=+91XXXXXXXXXX
CALLMEBOT_WA_APIKEY=
NTFY_TOPIC=
HEALTHCHECKS_PING_URL=
DASHBOARD_USER=admin
DASHBOARD_PASS=
```

---

## 10. Project structure

```
Monitor/
├── CLAUDE.md
├── PLAN.md
├── docs/
│   └── progress.md          # proof log: each step's commands + real output
├── README.md
├── config.yaml
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── app/
│   ├── main.py              # FastAPI app + startup of monitor loop
│   ├── config.py            # pydantic settings, loads yaml + env
│   ├── models.py            # dataclasses / pydantic models
│   ├── db.py                # SQLite access, migrations, retention
│   ├── monitor/
│   │   ├── prober.py        # ICMP + TCP probes, canaries
│   │   ├── state.py         # state machine, debounce, flap
│   │   └── scheduler.py     # asyncio loop
│   ├── alerts/
│   │   ├── manager.py       # escalation, repeat, ACK, dedupe
│   │   ├── base.py          # Notifier interface
│   │   ├── telegram.py      # text, voice note, bot commands, ACK button
│   │   ├── callmebot.py     # Telegram call + WhatsApp
│   │   ├── ntfy.py
│   │   └── email.py
│   ├── web/
│   │   ├── routes.py        # REST + WebSocket
│   │   ├── templates/index.html
│   │   └── static/ (css, js)
│   └── heartbeat.py         # healthchecks.io ping
├── scripts/
│   └── test_alerts.py       # fire a test alert on every channel
└── tests/
```

---

## 11. Build phases

| Phase | Deliverable | Done when |
|---|---|---|
| 0. Setup | Repo, venv, config loader, `.env.example`, Telegram bot created, CallMeBot authorised, healthchecks.io check created | `python scripts/test_alerts.py` delivers on every channel |
| 1. Probe core | ICMP + TCP prober, canaries, console output | Prints RTT/loss for both routers every 10s |
| 2. State engine | Debounce, flap, site-isolated, unit tests | Tests pass using a fake prober (simulated outages) |
| 3. Storage | SQLite schema, write results/events, retention job | History queryable |
| 4. Alerts | Notifier interface, Telegram, CallMeBot call + WA, ntfy, escalation, ACK, recovery msg | Simulated DOWN triggers full escalation; ACK stops repeats |
| 5. Dashboard | FastAPI routes, WebSocket, tiles, RTT chart, availability bar, event log | Blocking a target IP (Windows firewall rule) turns tile red live within ~40s |
| 6. Ops extras | Bot commands, maintenance mode, daily summary, heartbeat, basic auth | `/status` answers in Telegram; killing the process triggers healthchecks.io alert |
| 7. Packaging | Dockerfile, compose, healthcheck, README | `docker compose up` locally shows live dashboard |
| 8. Cloud deploy | OCI VM, Docker, Tailscale Funnel, backups (runbook 12.5) | Dashboard reachable from phone over internet; VM reboot recovers unattended; outage test fires alerts |

**Rule for every phase: test, prove, then move on.** Each phase is built in small steps. After each step the step is tested and proven with the real command output, and the proof is logged in `docs/progress.md`. The next step starts only after the current one passes. Bugs are handled the same way: prove it is broken (failing test/output), fix, prove it is fixed with the same test. Code stays simple (see CLAUDE.md, Code style).

Testing tip: to simulate an outage without touching production, add a test target like `192.0.2.1` (TEST-NET, never answers) or add an outbound Windows Firewall block rule for one router IP.

---

## 12. Deployment: 24x7, dashboard on the internet (free)

### 12.1 Why not Vercel

Vercel is built for websites and short serverless functions, not for a process that runs all the time.

| Need | Vercel (Hobby, free) |
|---|---|
| Probe every 10s, forever | No background process. Functions run per request and stop. Hobby cron runs **once per day** at most. |
| ICMP ping | No raw sockets in serverless functions, so real ping is not possible. |
| SQLite history | No persistent disk. Files vanish between invocations. |
| Live WebSocket dashboard | Serverless functions do not hold WebSocket connections. |
| Docker container | Vercel does not run Docker containers. |

Networking analogy: Vercel is like a stateless ACL hit, something that happens per packet and forgets. A monitor is like a routing protocol, which needs a process that stays up and keeps state (hello timers, neighbour table). Other "free" app hosts (Render free, Koyeb free, Hugging Face Spaces) put apps to sleep when idle and usually block ICMP, so they fail the same way.

**Decision:** run the whole app as **one Docker container on a free always-on Linux VM**. The container runs the prober, the alerting, and the dashboard together.

### 12.2 Target platform: Oracle Cloud Always Free VM

| Item | Choice |
|---|---|
| Cloud | Oracle Cloud Infrastructure (OCI) Always Free |
| Region | India West (Mumbai) or India South (Hyderabad) |
| Shape | `VM.Standard.A1.Flex` (ARM, 1 OCPU / 6 GB) or `VM.Standard.E2.1.Micro` (AMD, 1 GB). Either is enough for this app. |
| OS | Ubuntu 24.04 LTS |
| Runtime | Docker Engine + Docker Compose plugin |
| Container | `monitor` (FastAPI + probe loop), `restart: unless-stopped`, `cap_add: [NET_RAW]`, volume `monitor_data:/data` for SQLite |
| Public access | HTTPS URL via **Tailscale Funnel** (free, stable `https://<vm-name>.<tailnet>.ts.net`, no inbound ports opened) |
| Auth | Dashboard login (basic auth or session login) is **mandatory** because it is on the internet |
| Watchdog | healthchecks.io heartbeat (already in plan) alerts on Telegram if the VM or container dies |

Fallback host if Oracle signup or capacity is a problem: Google Cloud `e2-micro` free tier (US regions only, 1 GB RAM), same container, same steps.

Bonus: the monitor now probes from a cloud data centre instead of home broadband. That makes it an independent vantage point, and home internet drops no longer cause false alarms.

### 12.3 Deployment topology

```
 Internet users (you, team)                       Telegram / CallMeBot / ntfy / healthchecks.io
        |  HTTPS                                                ^
        v                                                       | outbound HTTPS alerts
 Tailscale Funnel (https://monitor-vm.<tailnet>.ts.net)         |
        |                                                       |
 +------v---------------- OCI VM (Ubuntu, Always Free) ---------+------+
 |  tailscaled  --->  127.0.0.1:8080                                   |
 |                   +---------------------------------------------+  |
 |                   | Docker container "monitor"                  |  |
 |                   |  FastAPI dashboard + WebSocket (port 8080)  |  |
 |                   |  asyncio probe loop  --ICMP/TCP-->  Internet ----> 32.142.239.74
 |                   |  alert manager                              |  |       32.132.149.134
 |                   |  SQLite on volume /data                     |  |
 |                   +---------------------------------------------+  |
 +--------------------------------------------------------------------+
```

The container publishes port 8080 on `127.0.0.1` only. Nothing is exposed directly on the VM's public IP except SSH (restricted to your IP).

### 12.4 Container spec

- Base image `python:3.12-slim`, install `iputils-ping` (fallback prober), `sqlite3` (backups) and `tzdata`.
- Run as non-root user; grant `NET_RAW` capability for ICMP.
- `HEALTHCHECK` hits `/healthz`; Docker restarts the container if unhealthy.
- All settings from `/app/config.yaml` (mounted read-only) and `.env` (via `env_file`).
- SQLite at `/data/monitor.db` on a named volume so data survives rebuilds.
- Log to stdout; `docker compose logs -f` to view. Limit log size (`max-size: 10m`, `max-file: 3`).
- Build on the VM itself (`docker compose up -d --build`) so ARM vs AMD architecture does not matter.

`docker-compose.yml` (target):
```yaml
services:
  monitor:
    build: .
    container_name: monitor
    restart: unless-stopped
    cap_add: [NET_RAW]
    env_file: .env
    environment:
      - TZ=Asia/Kolkata
    volumes:
      - monitor_data:/data
      - ./config.yaml:/app/config.yaml:ro
    ports:
      - "127.0.0.1:8080:8080"
    logging:
      options: { max-size: "10m", max-file: "3" }
volumes:
  monitor_data:
```

### 12.5 Step-by-step deployment runbook

1. **Create OCI account** (card needed for identity check, not charged on Always Free). Home region: Mumbai or Hyderabad (cannot be changed later).
2. **Create VM:** Ubuntu 24.04, shape from 12.2, add your SSH public key, assign a public IPv4.
3. **Network:** in the VCN Security List allow ingress TCP/22 **from your IP only**. No 80/443 needed (Funnel is outbound). Egress: allow all (default), so ICMP and HTTPS alerts work.
4. **SSH in and harden:** `sudo apt update && sudo apt upgrade -y`, enable unattended-upgrades, keep Oracle's default iptables rules (they already block everything but SSH).
5. **Install Docker:** Docker Engine + compose plugin from Docker's official apt repo; add user to `docker` group.
6. **Sanity check from the VM:** `ping -c 5 32.142.239.74` and `ping -c 5 32.132.149.134`. Both IPs answer ICMP from any internet source, so no whitelisting is needed. This step only confirms the VM's egress works.
7. **Deploy app:** `git clone` the repo (private repo, or copy with `scp`), create `.env` and `config.yaml` on the VM (never commit them), then `docker compose up -d --build`.
8. **Verify locally on VM:** `curl -s localhost:8080/healthz`, `docker compose logs -f` shows probe results every 10s.
9. **Publish dashboard:** install Tailscale on the VM, `sudo tailscale up`, then `sudo tailscale funnel --bg 8080`. Open the `https://...ts.net` URL from any browser, log in.
10. **Test alerts:** `docker compose exec monitor python scripts/test_alerts.py`.
11. **Test an outage:** temporarily add target `192.0.2.1` in config, restart, confirm DOWN alert + voice call + red tile, then remove it.
12. **Watchdog:** confirm healthchecks.io shows the check green; `docker compose stop` for 3 minutes and confirm you get the "monitor down" alert.

### 12.6 Operations

| Task | Command |
|---|---|
| Update to new version | `git pull && docker compose up -d --build` |
| View logs | `docker compose logs -f --tail 200` |
| Restart | `docker compose restart` |
| Backup DB (daily cron on VM) | `docker compose exec monitor sqlite3 /data/monitor.db ".backup /data/backup-$(date +%F).db"`, keep last 7 |
| Survives VM reboot | Yes: Docker service enabled + `restart: unless-stopped`; Tailscale Funnel `--bg` persists |

### 12.7 Oracle free tier gotchas

- **Idle reclamation (applies on the free plan):** Oracle can reclaim Always Free VMs that stay very idle (CPU, network and memory all under 20% at the 95th percentile over 7 days). This monitor is light, so it could be flagged. Decision for now: **stay on the free plan** and accept the risk, with these safeguards:
  - healthchecks.io alerts on Telegram within minutes if the VM stops, so it is never a silent failure.
  - Everything needed to rebuild is in git (code, `config.example.yaml`, `.env.example`) plus a copy of `.env` kept safely offline, so runbook 12.5 rebuilds a fresh VM in about 15 minutes.
  - Weekly DB backup copied off the VM (e.g. `scp` to your PC) so history is not lost.
  - Do not run "keep-busy" CPU burner scripts to dodge the check; it wastes resources and goes against Oracle's terms.
- **Upgrade path:** when you move to paid, see section 12.9.
- **ARM capacity:** A1 shapes are sometimes "out of capacity" in a region. Use the E2.1.Micro AMD shape instead; it is enough.
- **Home region is permanent;** Always Free VMs only run in the home region.

### 12.8 Optional: Vercel for the dashboard only (not recommended now)

A static dashboard on Vercel could read `/api/status` from the VM. It adds CORS, auth across two hosts, and a second deployment for no real gain, since FastAPI already serves the dashboard. Revisit only if a public status page for customers is needed.

### 12.9 Later: moving to a paid plan

Current decision: **free plan only.** When budget allows, these upgrades give the most value, in order:

| Upgrade | Cost (approx.) | What it fixes |
|---|---|---|
| OCI account to Pay As You Go | ₹0 if you stay inside Always Free limits | Removes idle-reclamation risk. Set a budget alert (e.g. ₹100) first. |
| Real PSTN phone call alerts (Twilio / Exotel / Plivo) | Pay per call | Rings a normal phone number even without internet data on the phone; more reliable than CallMeBot. Add as a new `Notifier`, no redesign. |
| WhatsApp Cloud API (Meta, official) | Per-conversation pricing | Official, reliable WhatsApp alerts instead of CallMeBot. |
| Own domain + Cloudflare | Domain ~₹800/year | Branded URL (e.g. `monitor.yourdomain.com`) via Cloudflare Tunnel instead of `ts.net`. |
| Second probe location (another small VM) | Low | Multi-vantage checks: alert only when both locations agree, fewer false alarms. |

The app design does not change for any of these: each is a config change, a new notifier class, or a second copy of the same container.

---

## 13. Risks and decisions

| Risk | Mitigation |
|---|---|
| False DOWN from ICMP deprioritisation / rate limit on router | TCP fallback, 3-packet probe, debounce |
| Monitor's own ISP outage | Canaries + suppress + healthchecks.io; cloud VM vantage point |
| Dashboard exposed on internet | Mandatory login, HTTPS only via Funnel, container bound to 127.0.0.1, SSH limited to own IP |
| Oracle reclaims idle free VM (free plan) | healthchecks.io alert, 15-min rebuild runbook, off-VM backups; move to PAYG later (12.9) |
| VM/container dies | Docker restart policy + healthchecks.io dead-man alert |
| CallMeBot rate limit or outage | Telegram Bot API primary, ntfy backup |
| Alert storm on flapping link | Flap detection, dedupe, repeat interval |
| Secrets leak | `.env` in `.gitignore`, only `.env.example` committed |
| Customer IPs in a public repo | Keep real `config.yaml` out of git (commit `config.example.yaml`) |

## 14. Build vs. existing free tool

**Uptime Kuma** (open source, self-hosted) already does ping monitors, a status dashboard, and Telegram/WhatsApp/ntfy notifications. It is a good fallback or benchmark. Building this custom tool is still worthwhile for: site-isolated logic, canary suppression, voice-call escalation with ACK, and as a portfolio project.

## 15. Future enhancements

SNMP (interface status, CPU), BGP neighbour state via SSH/NETCONF, traceroute snapshot attached to DOWN alert (shows where the path breaks), multi-vantage probing, LLM-generated incident summary on recovery, auto-create ServiceNow incident, Prometheus exporter + Grafana.
