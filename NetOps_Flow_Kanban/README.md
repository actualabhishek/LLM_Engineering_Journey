# NetOps Flow

A Kanban board for network and IT operations teams, with an AI assistant that can change the board for you. Cards are change requests, incidents and tasks; they carry a ticket id, priority, assignee, due date and CAB approval windows.

The whole thing runs as one Docker container: a FastAPI process serves the API and the built frontend from the same origin, backed by SQLite.

## Run

Put your OpenRouter key in `.env` at the project root (see `.env.example`):

```
OPENROUTER_API_KEY=your-key
```

Then start it:

```
scripts/start.sh     # Mac / Linux
scripts\start.bat    # Windows
```

Open http://localhost:8000 and sign in with `user` / `password`.

To stop:

```
scripts/stop.sh      # Mac / Linux
scripts\stop.bat     # Windows
```

Board data lives in the `netops-flow-data` Docker volume and survives restarts.

## What it does

**Board.** Four columns, each renamable in place. Cards drag between and within columns, and the order sticks. Add a card from the column, edit or delete it from the card. A search box filters by title or ticket id, and a stats strip counts open changes, active P1/P2 incidents, SLA risk and deployments this week.

**AI assistant.** The sidebar takes plain instructions and acts on the board: create a card, edit one, move one between columns, rename a column, or several at once. The board state goes to the model with each message, so it can refer to cards by ticket id. Actions it returns are validated and applied against the same database as the UI, with the same ordering and uniqueness rules. If an action cannot be applied, the reply says how many were skipped rather than claiming success.

**Dark theme.** Built on CSS variable tokens rather than per-component colours, with three surface levels carrying depth instead of shadows, which do not read on a dark background.

**Persistence.** Everything is SQLite. The schema supports multiple users even though the MVP signs in one, and the database survives container restarts.

## How it is put together

- **Frontend** - Next.js 16 and React 19, Tailwind 4, drag and drop via dnd-kit. Built as a static export, so there is no Node process at runtime.
- **Backend** - FastAPI on Python 3.13. Serves `/api/*` and mounts the static export at `/`, with API routes matched first. Bearer-token sessions; passwords are salted PBKDF2.
- **AI** - OpenRouter. The model returns a small JSON list of actions, which the backend validates and executes. No agent framework.
- **Packaging** - One multi-stage Dockerfile: Node builds the frontend, Python runs the app. SQLite lives on a mounted volume, and `OPENROUTER_API_KEY` is passed in from `.env`.

Because the built app talks to the API on relative paths, there is one origin in production and nothing to configure between frontend and backend. CORS is scoped to the dev servers.

## Development

Install once:

```
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
cd frontend && npm install
```

Then run the two halves separately:

```
cd backend && .venv/bin/uvicorn app.main:app --reload    # :8000
cd frontend && npm run dev                               # :3000
```

On Windows the venv puts these in `.venv\Scripts\` instead. In dev the
frontend calls the backend on `http://localhost:8000`, and the database is
`backend/app.db` rather than the container volume.

Tests:

```
cd frontend && npm test              # unit
cd frontend && npx playwright test   # end to end
```

The end-to-end suite starts its own dev server, or set `E2E_BASE_URL=http://localhost:8000` to run it against the container. It creates and cleans up its own cards, so it can run repeatedly against a database that already has data.

## Layout

- `frontend/` - Next.js app, built to static files
- `backend/` - FastAPI app, serves the API and the built frontend
- `scripts/` - start and stop scripts
- `docs/` - the build plan and what was done after it

`Claude.md` holds the requirements and technical decisions; `docs/PLAN.md` records how it was built and the issues fixed since.

Still learning. Still building.
