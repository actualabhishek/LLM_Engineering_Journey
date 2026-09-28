# CLAUDE.md

**Hotel Experience Assistant**: a voice concierge (English + Hindi) for booking, loyalty, check-in and recommendations. Guests only talk; the assistant talks back. Two parts: the **app** (Docker, CPU, on a PC without GPU) and a **GPU worker** (Modal, T4) that runs the speech models. The full plan is in `docs/PLAN.md`; read it before starting any work.

## Rules
1. Use the latest stable versions of libraries and idiomatic approaches as of today. Check current docs (context7, Modal docs, Hugging Face model cards) instead of relying on memory.
2. Keep it simple. NEVER over-engineer, ALWAYS simplify, NO unnecessary defensive programming. No extra features beyond `docs/PLAN.md`.
3. Be concise, in code and in replies.
4. Test after each phase and prove it works: record the commands and their real output in `docs/progress.md`.
5. When debugging: first prove what is broken (failing test or output), then fix it, then prove it is fixed by running the same test or command again.

## Stack
- App backend: Python, FastAPI, SQLAlchemy + Alembic, SQLite, `uv` (never pip). Code in `backend/`. No ML models in the app.
- App frontend: Next.js static export, TypeScript, Tailwind, `@ricky0123/vad-web` (Silero VAD in the browser). Code in `frontend/`. FastAPI serves the built files.
- LLM: OpenRouter via the `openai` SDK, `base_url=https://openrouter.ai/api/v1`, key `OPENROUTER_API_KEY`, model from `LLM_MODEL`.
- GPU worker: `gpu_worker/modal_app.py` on Modal (T4). `faster-whisper` `large-v3-turbo` for STT, Kokoro-82M (English) and Indic Parler-TTS (Hindi) for TTS. Endpoints `POST /transcribe`, `POST /speak`, bearer token `GPU_WORKER_TOKEN`. The app calls it via `GPU_WORKER_URL`.

## Commands
```bash
cd backend && uv sync && uv run pytest              # app backend tests
cd backend && uv run fastapi dev app/main.py        # app dev server
cd frontend && npm install && npm run dev
cd frontend && npx playwright test                  # E2E (fake microphone)
modal deploy gpu_worker/modal_app.py                # deploy GPU worker
uv run --with httpx python gpu_worker/test_worker.py   # prove the worker works
docker build -t hotel-assistant . && docker run -p 8000:8000 --env-file .env -v hotel_data:/data hotel-assistant
```

## Design rules
- Business rules live in `backend/app/services/`. API, voice and agent code call services; they don't contain business rules or SQL.
- Tools take the guest's identity from the session, never from LLM arguments.
- Tools that change data return a summary first. The change runs only after the guest says yes, and the server runs the stored pending action.
- The guest UI has no text input. Captions are always shown.
- Hindi replies are in Devanagari. The app converts numbers, prices and dates to words before sending text to `/speak`.
- The worker only does speech (STT/TTS). No business logic there.
- Never ask for, accept or store card details. Never save audio.
- Money is integer paise.
- Secrets: `.env` for the app (add every new variable to `.env.example`), Modal secrets for the worker.
- Don't use Google Colab to serve anything; it's only for prototyping in a notebook.

## Workflow
- Work phase by phase from `docs/PLAN.md`. Start each phase in Plan Mode and wait for approval.
- Sub-agents are in `.claude/agents/`: `backend-engineer`, `llm-agent-engineer`, `voice-engineer`, `frontend-engineer`, `test-engineer`, `security-reviewer`. Run `test-engineer` and `security-reviewer` before closing a phase.
- Small commits with Conventional Commit messages.
- If a business rule is unclear, ask. Don't invent hotel policies.
