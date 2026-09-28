# Hotel Experience Assistant: Plan

A voice concierge for a hotel. Guests **talk** to it hands-free and it **talks back**, in English or Hindi, to book rooms, check loyalty points, check in before arrival, and get recommendations. The screen shows live captions and a summary card; guests never type. Staff get a small admin page.

## Principles
- Latest stable versions of every library, idiomatic usage.
- Simplest thing that works. No over-engineering, no speculative features, no unnecessary defensive code.
- Every phase ends with proof that it works (tests + recorded real output).

## Architecture: two parts

```
Browser ──WebSocket──▶ App (Docker on your PC, CPU) ──HTTPS──▶ GPU worker (Modal, T4)
  mic + VAD               UI, API, SQLite, agent                  Whisper STT
  speaker                 LLM calls (HF Inference Providers)      Kokoro TTS (English)
                                                                   Indic Parler-TTS (Hindi)
```

1. **App (Docker, CPU only).** Web UI, WebSocket, backend, SQLite, agent loop. No ML models, so the image is small and runs on any PC or cheap VM.
2. **GPU worker (Modal serverless GPU).** One Python file that loads the Hugging Face speech models on a T4 and exposes two HTTPS endpoints: `POST /transcribe` and `POST /speak`. It scales to zero when idle. Modal's free $30/month covers development (a T4 is about $0.59/hour).

The app only knows `GPU_WORKER_URL` and `GPU_WORKER_TOKEN`, so the worker can move later (another GPU host) by changing one setting.

**Google Colab** can be used to prototype the worker code interactively in a notebook. It is not used to serve the worker: Colab's terms don't allow running web services or tunnels from it, and sessions are time-limited.

## Stack

| Part | Choice |
|---|---|
| App backend | Python, FastAPI, SQLAlchemy + Alembic, SQLite, `uv` |
| App frontend | Next.js (static export), TypeScript, Tailwind. Served by FastAPI |
| Voice activity (in browser) | Silero VAD via `@ricky0123/vad-web` |
| LLM | OpenRouter via the `openai` SDK (`base_url=https://openrouter.ai/api/v1`, `OPENROUTER_API_KEY`). Default `openai/gpt-oss-120b` (cheap: $0.03/$0.17 per M input/output tokens) |
| Speech-to-text (worker) | `openai/whisper-large-v3-turbo` via `faster-whisper` (English, Hindi, Hinglish) |
| Text-to-speech (worker) | English: `hexgrad/Kokoro-82M` (voice `af_heart`). Hindi: `ai4bharat/indic-parler-tts` (speaker `Divya`) |
| GPU worker hosting | Modal, T4 GPU |

## Features

1. **Voice conversation.** Tap "Start" once, then talk hands-free. VAD in the browser detects when the guest finishes speaking and sends that utterance. The guest can interrupt the assistant at any time (barge-in: the browser stops playback when VAD hears speech). Replies are short and are spoken sentence by sentence, so speech starts quickly. The language (English or Hindi) is detected each turn and the reply uses the same language.
2. **Booking.** Check availability and price, create, modify and cancel bookings. Payment is at the hotel.
3. **Loyalty.** Show tier and points, explain benefits, enroll, redeem points for a stay.
4. **Check-in.** Pre-arrival check-in: confirm details, arrival time and special requests.
5. **Recommendations.** Dining, spa, amenities and local tips, personalized from the guest's stated preferences.
6. **Admin page.** Password login. Lists bookings, check-ins and conversation transcripts.

**Identity:** a guest reaches an existing booking with **booking reference + last name**, and loyalty with **member number + last name**, both spoken. Booking references use letters and digits that are easy to say (no 0/O, 1/I/L).

**Hotel knowledge:** one Markdown file (`backend/app/kb/hotel.md`) with rooms, amenities, dining, policies and local tips. It is small enough to go into the system prompt directly, so there is no vector database.

## How a turn works

```
browser VAD → utterance audio → WebSocket → app → worker /transcribe → agent (LLM + tools)
  → reply split into sentences → worker /speak (per sentence) → WebSocket → browser plays
```

- **Agent:** one tool-calling loop with the `openai` SDK. Tools: `check_availability`, `create_booking`, `find_booking`, `modify_booking`, `cancel_booking`, `loyalty_status`, `enroll_loyalty`, `redeem_points`, `check_in`, `save_preferences`.
- **Business rules live in services**, not in the LLM. Tools get the guest's identity from the session, not from LLM arguments.
- **Confirmation:** tools that change data (`create_booking`, `modify_booking`, `cancel_booking`, `enroll_loyalty`, `redeem_points`, `check_in`) first return a summary that the assistant reads out. The change runs only after the guest says yes. The server stores the pending action and runs exactly that action, not a new guess by the LLM.
- **Hindi:** Hindi replies are written in Devanagari so the TTS reads them correctly. Numbers, prices (₹) and dates are converted to words before TTS (done in the app).
- **Cold start:** when a guest taps Start, the app pings the worker so the models load while the greeting plays. After ~5 minutes idle the worker scales to zero; the first request after that takes roughly 30–60 s. For demos, keep one container warm.
- **Card numbers:** the assistant never asks for or accepts card details.

## Data (SQLite)
`room_types`, `inventory` (date × room type), `guests`, `bookings`, `loyalty_accounts`, `loyalty_transactions`, `checkins`, `conversations`, `messages`. Money is stored as integer paise. Seed data: a fictional hotel, 5 room types, 60 days of inventory, 3 loyalty tiers, a few demo guests.

## Security & privacy (kept to what matters)
- Secrets from environment variables only (`.env` for the app, Modal secrets for the worker; never committed).
- The worker requires a bearer token (`GPU_WORKER_TOKEN`) on every request.
- Admin password from `ADMIN_PASSWORD`; session cookie is HttpOnly and Secure.
- Audio is processed in memory by the app and the worker and never saved. Transcripts are kept for the admin page.
- A short on-screen notice before the first conversation says an AI assistant is processing the conversation.
- The microphone works on `http://localhost`. If the app is later hosted elsewhere, put it behind HTTPS (Caddy, Nginx or a cloud load balancer).

## Repository layout

```
Hotel_Experience_Assistant/
├── CLAUDE.md
├── README.md
├── Dockerfile               # the app (CPU)
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── PLAN.md
│   └── progress.md          # proof of each phase
├── backend/                 # the app's Python code
│   ├── pyproject.toml
│   ├── alembic/
│   ├── app/
│   │   ├── main.py          # FastAPI app, static files
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── seed.py
│   │   ├── api/             # REST: admin, health
│   │   ├── services/        # booking, loyalty, checkin
│   │   ├── agent/           # loop, tools, prompt
│   │   ├── voice/           # websocket, worker client, number/date normalization
│   │   └── kb/hotel.md
│   └── tests/
│       └── fixtures/        # recorded en/hi audio clips
├── frontend/
│   ├── app/                 # / (voice), /admin
│   ├── components/
│   ├── lib/                 # websocket, VAD, playback
│   └── tests/               # Playwright
└── gpu_worker/
    ├── modal_app.py         # STT + TTS on a T4, /transcribe and /speak
    └── test_worker.py       # calls the deployed worker with fixture audio
```

## Environment
App (`.env.example`):
```
OPENROUTER_API_KEY=
LLM_MODEL=openai/gpt-oss-120b
GPU_WORKER_URL=
GPU_WORKER_TOKEN=
ADMIN_PASSWORD=
SECRET_KEY=
DATABASE_URL=sqlite:////data/app.db
```
Worker (Modal secret `hotel-worker`): `GPU_WORKER_TOKEN`, `HF_TOKEN` (the latter needed at image-build time to download the gated `ai4bharat/indic-parler-tts` model).

## Running it

**GPU worker (once, and after changes):**
```bash
pip install modal && modal setup          # one-time login
modal secret create hotel-worker GPU_WORKER_TOKEN=<random> HF_TOKEN=<your HF token>
modal deploy gpu_worker/modal_app.py      # prints the HTTPS URL → GPU_WORKER_URL
```

**App:**
```bash
docker build -t hotel-assistant .
docker run -d -p 8000:8000 --env-file .env -v hotel_data:/data hotel-assistant
# open http://localhost:8000
```
The Dockerfile is multi-stage: build the Next.js static site, then a slim Python image with `uv`. It runs as a non-root user, runs migrations and seeds on start, and has a `HEALTHCHECK` on `/health`.

## Phases

Each phase ends with tests passing and **proof** written to `docs/progress.md`: the commands run and their real output (test results, curl responses, transcripts, screenshots, audio file names). If something breaks: show the failing test or output first, fix it, then show the same test passing.

| # | Phase | Proof |
|---|---|---|
| 1 | **Scaffold + Docker.** App skeleton; container serves the page and `/health` | `docker run` + `curl /health` output |
| 2 | **GPU worker.** `modal_app.py` with `/transcribe` and `/speak`, deployed to Modal | `test_worker.py` output: English and Hindi fixture transcripts, generated `.wav` files, latency (cold and warm) |
| 3 | **Data + services.** Models, migrations, seed, booking/loyalty/check-in services | pytest output; a scripted booking → modify → cancel run |
| 4 | **Agent (text).** LLM loop, tools, confirmation step, prompt with hotel KB | pytest with a fake LLM; one real multi-turn transcript in English and one in Hindi |
| 5 | **Voice end to end.** WebSocket, worker client, normalization, browser VAD, playback, barge-in, captions and cards | script streams a fixture over the WebSocket and saves the spoken reply; Playwright test with Chromium's fake microphone completes a booking by voice; screenshot |
| 6 | **Admin page + finish.** Admin login and lists, README | Playwright run against the Docker container; README steps followed from scratch |

## Done means
- A guest completes every feature above by voice only, in English and in Hindi.
- The app runs from one `docker run` on a PC without a GPU; the worker runs on Modal.
- All tests pass and `docs/progress.md` has proof for every phase.

---

Part of the `llm-engineering-journey` portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.
