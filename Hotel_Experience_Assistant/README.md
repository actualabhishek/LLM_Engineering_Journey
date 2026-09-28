# Hotel Experience Assistant

A voice concierge for hotels: guests talk (English or Hindi) to book rooms, manage loyalty points, check in, and get recommendations, and the assistant talks back. The app runs as one Docker container on a CPU-only machine; speech (STT/TTS) runs on a serverless GPU worker on Modal.

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

Part of the `llm-engineering-journey` portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.
