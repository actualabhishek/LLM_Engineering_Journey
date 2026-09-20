# Project Management App

## Business Requirements

- A user can sign in
- When signed in, the user sees a Kanban board representing their project
- The Kanban board has fixed columns that can be renamed
- The cards on the Kanban board can be moved with drag and drop, and edited
- There is an AI chat feature in a sidebar; the AI is able to create / edit / move one or more cards

## Limitations

- For the MVP, there will only be a user sign in (hardcoded to `user` and `password`) but the database will support multiple users for future
- For the MVP, there will only be 1 Kanban board per signed in user
- For the MVP, this will run locally (in a Docker container)

## Technical Decisions

- NextJS frontend
- Python FastAPI backend, including serving the static NextJS site at `/`
- Everything packaged into a Docker container
- Use OpenRouter for the AI calls. An `OPENROUTER_API_KEY` is in `.env` in the project root
- Use `inclusionai/ling-3.0-flash-vl:free` model. It does not accept `response_format`, so the request omits it and relies on the prompt for bare JSON (verified: 6/6 clean responses, no markdown fences). History: `qwen/qwen3.8-27b:free` and `google/gemma-4-26b-a4b-it:free` were stuck on 429s from their upstream providers; `deepseek/deepseek-v4-flash-0731:free` replaced them, then was withdrawn from the free tier (OpenRouter returns 404 pointing at the paid slug)
- Use SQLite for the local database, creating a new db if it doesn't exist. `DB_PATH` overrides its location; the container points it at a Docker volume so data survives restarts
- Start and Stop server scripts for Mac, PC, Linux in `scripts/`
- The frontend is a Next.js static export (`output: "export"`) that FastAPI serves from `/`. The built app calls the API on relative paths, so everything is one origin
- Dark theme. Colours are CSS variable tokens in `frontend/src/app/globals.css` exposed as Tailwind utilities (`bg-surface`, `text-muted`, `border-line`); components use those tokens rather than hardcoded colours
- Passwords are salted PBKDF2-HMAC-SHA256. Databases seeded before that are rehashed on startup, which is only safe while credentials are hardcoded
- CORS allows the dev servers only; the packaged app is same-origin and needs none

## Current state

Parts 1-9 of `docs/PLAN.md` are complete. The frontend is wired to the backend, both ship in one container, and the AI chat works. The twelve findings from a full code review have been fixed.

The frontend began as a standalone demo with its own dummy data. That is gone: the board now comes from `GET /api/board`, and `frontend/src/lib/seedData.ts` is dead code left from that era.

## Coding standards

1. Use latest versions of libraries and idiomatic approaches as of today
2. Keep it simple - NEVER over-engineer, ALWAYS simplify, NO unnecessary defensive programming. No extra features - focus on simplicity.
3. Be concise. Keep README minimal. IMPORTANT: no emojis ever
4. When hitting issues, always identify root cause before trying a fix. Do not guess. Prove with evidence, then fix the root cause.

## Testing

- `cd frontend && npm test` - unit tests
- `cd frontend && npx playwright test` - end to end. Starts its own dev server, or set `E2E_BASE_URL=http://localhost:8000` to run against the running container
- The e2e suite creates and tears down its own cards, so it can run repeatedly against a persistent database. It must stay that way

## Working documentation

All documents for planning and executing this project will be in the `docs/` directory. Please review the `docs/PLAN.md` document before proceeding.