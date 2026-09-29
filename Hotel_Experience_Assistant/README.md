# Hotel Experience Assistant

A voice concierge for hotels: guests talk (English or Hindi) to book rooms, manage loyalty points, check in, and get recommendations, and the assistant talks back. The app runs as one Docker container on a CPU-only machine; speech (STT/TTS) runs on a serverless GPU worker on Modal.

## What we built

A guest opens a web page, taps **Start**, and just talks — no typing, no forms. The assistant listens, replies out loud in the same language the guest used, and shows live captions plus a summary card whenever it actually does something (books a room, checks a guest in, redeems loyalty points). Before it changes anything real, it repeats back what it's about to do and only goes ahead once the guest says yes. There's also a small password-protected admin page to see bookings, check-ins, and past conversations.

## How it's built

Two moving parts:
- **The app** — a Python (FastAPI) backend and a Next.js frontend, packaged into one Docker container that runs on any regular CPU machine. It holds the hotel's data (rooms, bookings, loyalty accounts) in SQLite, runs the conversation logic, and serves the web page.
- **The GPU worker** — a separate serverless function on [Modal](https://modal.com) that only does speech: turning the guest's voice into text, and turning the assistant's reply back into speech. It spins up on demand and shuts down when idle, so there's no GPU running (or costing money) most of the time.

The two talk to each other over the network — the app never needs its own GPU.

## Models and AI used

- **The brain (LLM):** an open-weight model (`openai/gpt-oss-120b`) called through [OpenRouter](https://openrouter.ai). It decides what to say and which tool to use (check availability, make a booking, look up loyalty points, etc.) — the actual booking rules and database live in plain code, not in the model.
- **Speech-to-text:** `faster-whisper`, so the assistant can understand what the guest said, in English or Hindi.
- **Text-to-speech:** Kokoro for English, Indic Parler-TTS for Hindi — so the reply is actually spoken back.
- **Voice detection:** Silero VAD, running right in the guest's browser, to notice when they start and stop talking (and to let them interrupt the assistant mid-sentence).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- A [Modal](https://modal.com) account and its CLI: `pip install modal && modal setup`
- An [OpenRouter](https://openrouter.ai) account and API key (the LLM)

## 1. Configure the app

Copy the example environment file and fill it in:

```bash
cp .env.example .env
```

- `OPENROUTER_API_KEY` — your OpenRouter API key
- `LLM_MODEL` — default (`openai/gpt-oss-120b`) is fine
- `ADMIN_PASSWORD` — pick a password for the admin page
- `SECRET_KEY` — a random string (e.g. `openssl rand -hex 32`)
- `GPU_WORKER_URL` / `GPU_WORKER_TOKEN` — filled in after the next step

## 2. Deploy the GPU worker

```bash
modal secret create hotel-worker GPU_WORKER_TOKEN=<pick-a-random-token> HF_TOKEN=<your-hugging-face-token>
modal deploy gpu_worker/modal_app.py
```

This prints the worker's HTTPS URL. Put that URL and the token you chose into `.env` as `GPU_WORKER_URL` and `GPU_WORKER_TOKEN`.

## 3. Build and run the app

```bash
docker build -t hotel-assistant .
docker run -d -p 8000:8000 --env-file .env -v hotel_data:/data hotel-assistant
```

## 4. Use it

- `http://localhost:8000` — the guest voice page. Tap **Start**, allow the microphone, and talk.
- `http://localhost:8000/admin` — the admin page. Log in with `ADMIN_PASSWORD` to see bookings, check-ins and conversation transcripts.

## Development

The full technical plan is in [docs/PLAN.md](docs/PLAN.md); phase-by-phase proof (commands and real output) is in [docs/progress.md](docs/progress.md). Common dev commands:

```bash
cd backend && uv sync && uv run pytest              # app backend tests
cd backend && uv run fastapi dev app/main.py        # app dev server
cd frontend && npm install && npm run dev
cd frontend && npx playwright test                  # E2E (fake microphone)
```

---

Still learning, still building.

Part of the `llm-engineering-journey` portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.
