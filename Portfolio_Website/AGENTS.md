# AGENTS.md

## Overview

Personal site + AI "Digital Twin" for Abhishek Suman (Senior Network Engineer,
16+ yrs, transitioning into GenAI/LLM engineering). Two jobs: read as a
credible enterprise-grade engineering portfolio, and let visitors chat with an
AI agent grounded in his resume/profile. Repo is currently unscaffolded — no
`package.json` exists yet. This file is the single authoritative brief for
both agents and humans — the earlier `AGENT.md` (singular) has been folded in
here and removed to avoid two files drifting out of sync.

## Stack & structure (target — not yet scaffolded)

- Next.js, App Router, TypeScript — scaffold with `create-next-app`
- Tailwind CSS for styling; Framer Motion only for restrained micro-interactions
- Deploy target: Vercel — don't build in platform lock-in beyond standard
  Next.js API/route handlers
- No CMS, no database for v1 — content is structured TS/JSON checked into the repo
- Not a git repo yet (`git init` has not been run) — confirm with the user
  before initializing or making the first commit

## Commands

No build tooling exists yet. Once scaffolded via `create-next-app`, use the
scripts it generates in `package.json` (`dev`/`build`/`lint`) rather than
inventing different ones. Update this section with the real commands as soon
as `package.json` exists.

## Content source of truth

- `Abhishek_Suman_GenAI_LLM_Resume.pdf` and `Profile.pdf` at repo root are the
  **only** source for factual site copy (titles, dates, bullets, skills,
  first-person voice for the About/Hero sections).
- Do not invent achievements, metrics, employers, or projects not present in
  those PDFs.
- Both PDFs are git-ignored. Extract only what's meant to be public site copy
  into TS/JSON content files — do not commit the raw PDFs or dump their full
  text verbatim into client-visible source.

## Design direction — "enterprise edge"

- Palette: deep charcoal/slate/navy base, one restrained accent color (pick
  one — teal or amber — used sparingly for links/CTAs), off-white body text.
  No purple/blue gradient-hero SaaS clichés, no glassmorphism, no stock photos,
  no emoji in UI copy.
- Typography: a precise sans (Inter / IBM Plex Sans / Geist) for body text,
  optional monospace accent (JetBrains Mono / Geist Mono) for labels/metadata.
- Layout: dense, data-forward information architecture — "well-run internal
  dashboard," not a whitespace-heavy personal blog theme.
- Dark mode is the default and primary; light mode is optional.

## Digital Twin agent

- Server-side only: a Next.js Route Handler (e.g. `app/api/twin/route.ts`)
  reads `OPENROUTER_API_KEY` from `process.env` and calls OpenRouter's chat
  completions endpoint (`https://openrouter.ai/api/v1/chat/completions`).
  Never prefix this or any other secret with `NEXT_PUBLIC_`; never echo the
  key in client responses or error messages.
- System prompt must be built from a condensed, structured context file
  (e.g. `lib/twin-context.ts`), not the raw PDFs, and must instruct the model
  to answer in first person as Abhishek, stay within provided facts, and
  refuse/deflect prompt-injection attempts and off-topic requests (this is a
  public endpoint and a live prompt-engineering demo — treat injection
  resistance as a feature).
- Rate-limit the route (even a simple in-memory/edge limiter) since it's
  public and costs API credits.

**Two-model split (resolved):** `nvidia/nemotron-3.5-content-safety:free` is
a content-safety/moderation classifier, not a conversational model — it must
never be the model that generates the Twin's reply text, or output will be
malformed. Use it only as a guardrail pass (classify user input and/or the
draft reply as safe/unsafe; reject or soften on an unsafe verdict) — this
doubles as a deliberate "we take AI safety seriously" touch for the portfolio.
Pick a separate, currently-available free/cheap conversational OpenRouter
model (e.g. a current Llama, Qwen, or Gemma instruct model) for actually
generating replies — check `https://openrouter.ai/models?max_price=0` for
what's live at build time, since the free roster rotates. Both model IDs
should be named constants (e.g. in `lib/twin-context.ts` or an `env.ts`), not
hardcoded inline in the route handler, so swapping either later is a one-line
change.

## Env & secrets

- `.env` (git-ignored) holds `OPENROUTER_API_KEY`. Add `.env.example` with
  `OPENROUTER_API_KEY=` (no value) once scaffolding starts, so the repo is
  clonable without leaking the real key.
- Any future secret follows the same pattern: real value in `.env`,
  placeholder in `.env.example`, never committed, never `NEXT_PUBLIC_` unless
  the value is genuinely meant to be public.

## Non-goals

- No CMS, no database, no generic AI-startup visual clichés for v1.
- Digital Twin stays scoped to portfolio Q&A (career, skills, projects,
  availability) — not a general-purpose chatbot.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
