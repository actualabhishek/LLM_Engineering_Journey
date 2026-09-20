# Plan

This plan is executed part by part, in order. Each part ends with a "Proof of completion" step. Do not start the next part until that proof has been run and shown to pass. If something fails, find the root cause before changing anything (see Coding standards in CLAUDE.md).

## Status

Parts 1 to 9 are complete, each proved against a running app. Work done after the plan is recorded at the bottom.

## Part 1: Project scaffolding

Goal: a clean repo skeleton with nothing functional yet, but the right shape for everything that follows.

Tasks:
- Create `docs/`, `scripts/`, `backend/` directories at the project root
- Move the existing frontend-only demo into `frontend/` if not already there
- Add a root `.gitignore` covering Python, Node, SQLite db files, and `.env`
- Add a root `.env.example` listing `OPENROUTER_API_KEY=` (no real key committed)
- Confirm the real `.env` with the actual `OPENROUTER_API_KEY` exists at the project root and is gitignored
- Add a minimal root `README.md` describing the repo layout only (no feature docs)

Proof of completion:
- `git status` shows `.env` is ignored, not tracked
- Directory listing shows `frontend/`, `backend/`, `scripts/`, `docs/` at the root
- `frontend/` still runs standalone exactly as it did before (`npm run dev`, board loads with dummy data)

## Part 2: Backend skeleton and database

Goal: a FastAPI app that starts, and a SQLite schema that supports multiple users even though the MVP only uses one.

Tasks:
- Scaffold `backend/` as a Python project (FastAPI, uvicorn, latest stable versions)
- Define SQLite schema: `users`, `boards`, `columns`, `cards` tables. `users` supports multiple rows even though only one is seeded for the MVP
- On startup, create the SQLite db file if it doesn't exist, and seed one hardcoded user (`user` / `password`) with one board, the default columns, and the same dummy cards the frontend currently uses
- Add a `GET /api/health` endpoint returning a simple status payload
- No auth, no CRUD endpoints yet — just startup, schema, seed data, and the health check

Proof of completion:
- Deleting the SQLite file and restarting the backend recreates it with the seeded user, board, columns, and cards (verify by querying the db directly)
- `curl http://localhost:8000/api/health` returns a 200 with the expected payload
- Restarting the backend a second time does not duplicate the seed data

## Part 3: Authentication

Goal: sign-in works end to end against the backend, using the hardcoded credentials.

Tasks:
- Add `POST /api/login` that checks the submitted username/password against the `users` table (hardcoded row for the MVP) and returns a session token
- Add session validation (e.g. a bearer token checked on protected routes) — keep the mechanism simple, no need for refresh tokens or expiry logic beyond a sane default
- Protect all board/card endpoints (added in Part 4) behind this check
- Wire the frontend's sign-in screen to call `POST /api/login` and store the returned token, replacing any hardcoded/mock sign-in

Proof of completion:
- `curl -X POST /api/login` with `user`/`password` returns a valid token; wrong credentials return 401
- Calling a protected endpoint without a token returns 401
- Signing in through the actual frontend UI succeeds and reaches the board screen

## Part 4: Board and card API (CRUD)

Goal: the Kanban board's data is fully backed by the database, not dummy frontend state.

Tasks:
- `GET /api/board` — returns the signed-in user's board, its columns, and its cards
- `PATCH /api/columns/{id}` — rename a column
- `POST /api/cards`, `PATCH /api/cards/{id}`, `DELETE /api/cards/{id}` — create, edit (including moving between columns), delete
- All endpoints scoped to the authenticated user's own board

Proof of completion:
- A sequence of curl/pytest calls (create a card, move it to another column, rename a column, delete a card) leaves the database in the expected state, verified by re-fetching `GET /api/board`
- Restarting the backend preserves these changes (confirms persistence, not in-memory state)

## Part 5: Frontend wired to the real backend

Goal: the existing Kanban UI runs against the FastAPI backend instead of its own dummy data, with drag-and-drop and edit/delete calling the real endpoints.

Tasks:
- Replace the frontend's dummy data source with calls to `GET /api/board`
- Wire drag-and-drop to call the move/edit endpoint on drop
- Wire the add-card and delete-card UI to the real endpoints
- Wire column rename to the real endpoint
- Handle the signed-out state (no token) by redirecting to sign-in

Proof of completion:
- Manual walkthrough in the browser: sign in, see the seeded board, drag a card to another column, edit a card, delete a card, rename a column
- Reload the page after each action and confirm the change persisted (came from the database, not local state)

## Part 6: AI chat sidebar

Goal: the sidebar chat can create, edit, and move one or more cards on command, via OpenRouter.

Tasks:
- Add `POST /api/chat` on the backend: takes the user's message plus current board state, calls OpenRouter (`inclusionai/ling-3.0-flash-vl:free` — see Technical Decisions in Claude.md for why this replaced the originally specced model) with a system prompt describing the board and the available actions (create card, edit card, move card, rename column), and executes whatever actions the model returns against the real CRUD logic from Part 4
- Add the chat sidebar UI to the frontend: message list, input box, calls `POST /api/chat`, and refreshes the board after each response
- Keep the action format simple (e.g. the model returns a small JSON list of actions) — no need for a general-purpose agent framework

Proof of completion:
- Ask the chat "create a card called X in the Backlog column" and confirm the card appears on the board and in the database
- Ask it to move an existing card to a different column and confirm the move happened
- Ask it to edit a card's title and confirm the change
- A request with no valid action (e.g. small talk) does not corrupt the board

## Part 7: Single-container serving

Goal: FastAPI serves the built Next.js frontend as static files from `/`, so the whole app is one process.

Tasks:
- Add a Next.js static export/build step
- Mount the built frontend as static files on FastAPI's `/`, with `/api/*` untouched
- Confirm client-side routing still works when served this way

Proof of completion:
- Run only the backend (no `npm run dev`), visit `http://localhost:8000/`, and use the full app (sign in, board, chat) with no separate frontend process running

## Part 8: Docker packaging

Goal: the whole app runs from a single Docker container, started and stopped with simple scripts.

Tasks:
- Write a `Dockerfile` that builds the frontend, installs the backend, and runs uvicorn serving both `/api/*` and the static site
- Mount (or otherwise persist) the SQLite file so data survives container restarts
- Pass `OPENROUTER_API_KEY` into the container from the root `.env`
- Add `scripts/start.sh`, `scripts/stop.sh` (Mac/Linux) and `scripts/start.bat`, `scripts/stop.bat` (PC) that build/run and stop the container

Proof of completion:
- From a clean checkout, running the start script builds the image, starts the container, and the app is reachable in a browser with sign-in, board, and chat all working
- Stopping and restarting the container preserves board data
- The stop script actually stops the container (verify with `docker ps`)

## Part 9: End-to-end pass

Goal: everything works together, one more time, as a stranger would experience it.

Tasks:
- Fresh clone/copy of the project, real `.env` in place, run the start script only
- Walk through: sign in, view seeded board, drag/edit/delete cards, rename a column, use the AI chat to create and move a card, reload the page, stop and restart the container
- Fix anything that breaks, tracing each failure to its root cause before patching
- Trim the root `README.md` to the minimal run instructions (uses the start/stop scripts)

Proof of completion:
- The walkthrough above passes start to finish with no manual steps outside the start script and a browser

## After the plan

Changes made after Part 9, in order.

### Dark theme

The UI is now dark. It extends the existing navy palette rather than replacing it: the sidebar navy became the substrate for the whole app, and depth comes from three surface steps (field, surface, raised) because the light theme's shadows do not read on dark. Colours moved to CSS variable tokens so nothing is hardcoded per component. Priority chips gained dark text on bright fills, which also fixed a contrast failure (white on the amber was 3.3:1).

### Code review fixes

A full review of the application found twelve issues. All are fixed, each verified before and after:

1. Card reordering was never persisted. `update_card` wrote the position of the dragged card only, so positions collided and the old order returned on reload. Added `_reindex`, which renumbers an affected column as 0..n-1.
2. A rejected `fetchMe` left `checkingSession` true forever, rendering a blank page with no way out. Added a rejection handler.
3. Failed AI actions were swallowed while the reply still claimed success. Actions now report whether they applied, and the reply states how many did not.
4. The e2e suite mutated the seeded database, so it passed once and then failed. Tests now create and tear down their own cards, locate columns by key, and run serially.
5. Nothing kept ticket ids unique, so AI edit and move hit an arbitrary duplicate. Duplicates are rejected at both creation paths.
6. A failed card move stayed on screen until reload. Failed mutations now resync from the server.
7. `/api/me` returned 500 when a session outlived its user row. Returns 401.
8. A SQLite connection and a threadpool thread were held across the model call. The endpoint is async and releases the connection before awaiting.
9. Every sign-in failure read as bad credentials, including an unreachable backend. Each case has its own message.
10. CORS allowed every origin. Limited to the dev servers.
11. Passwords used unsalted single-round SHA-256 compared with `!=`. Now salted PBKDF2, compared in constant time, with existing databases rehashed on startup.
12. A missing `.env` failed only after a full image build. The start scripts check first.

### Known gaps

- `frontend/src/lib/seedData.ts` is dead code from the frontend-only demo
- Login skips the password hash when the username does not exist, so timing distinguishes a real username. Immaterial while credentials are hardcoded, relevant if the multi-user schema is ever used
- The AI model is on OpenRouter's shared free pool and returns 429 intermittently. The failure is logged and the board is left untouched
