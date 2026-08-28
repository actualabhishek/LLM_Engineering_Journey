# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## What this is

`postflow` — a local Claude Code plugin marketplace with one plugin: a Telegram-driven
LinkedIn content pipeline. Someone sends `Topic: <what you want the post about>` on
Telegram; Claude researches it, drafts a post in the `/my-brand` voice, generates an
image, sends both back to Telegram for `APPROVE`/`REJECT`, and on approval publishes to
LinkedIn via Playwright. There is no separate backend or daemon — the "listener" is a
live Claude Code session with the Telegram channel attached; nothing runs while no
session is open.

Full step-by-step pipeline logic lives in
`postflow-plugin/skills/postflow-pipeline/SKILL.md` — read that (not this file) for the
actual research/draft/image/approval/publish mechanics. `postflow-plugin/README.md`
covers install/configure. This file is only the standing session-startup contract.

## Session startup

Every session opened in this directory needs two things to actually work as intended:

1. **Launch with the Telegram channel attached** — a CLI flag, so it can only be set by
   whoever runs `claude`, not by anything inside a running session or by this file:

   ```
   claude --channels plugin:telegram@claude-plugins-official
   ```

   Without this flag, inbound Telegram messages never reach the session — `/postflow`
   will arm the listener but it won't receive anything. If a session was started without
   it, tell the user and don't pretend the listener is live.

2. **Arm the listener** — `.claude/settings.json` in this project has a `SessionStart`
   hook (`.claude/hooks/session-start-postflow.sh`) that injects an instruction to run
   `/postflow start` automatically at the start of every session here, so this normally
   happens without being asked. If for some reason it doesn't fire (hook disabled,
   `/hooks` not yet reloaded after this file was added), run `/postflow start` yourself
   at the start of the session.

`/postflow status` (or bare `/postflow`) reports what's armed, what's in flight, and
what's queued at any point.

## Requires (already installed/connected, not bundled here)

- `telegram@claude-plugins-official` — configured via `/telegram:configure`, paired via
  `/telegram:access`.
- `playwright@claude-plugins-official` — publishes to LinkedIn.
- The Airtable MCP connector (claude.ai connector) — the `Posts` tracking table,
  base `app2FBJB0YQw5GcV4`, table `tblJS8x1EWQHp5ZvY`.
- `~/.claude/commands/my-brand.md` — read, never modified, for the drafting step.
- `postflow-plugin/.env` (copy from `.env.example`) — `OPENROUTER_API_KEY` (image
  generation via OpenRouter's Gemini image model) and `CLOUDINARY_URL` (image hosting).

## Gotchas

- **No inline-keyboard/button approval.** Two mechanisms were tried and dropped —
  see "Why approval is a text reply, not a button" in `postflow-plugin/README.md`.
  Approval is a plain-text `APPROVE`/`REJECT` reply; never construct a `reply_markup`.
- **Only one topic in flight at a time.** Everything else queues in
  `postflow-plugin/scripts/state.mjs` and is processed strictly in order — never
  interleave two runs' Telegram messages.
- **LinkedIn publish needs a one-time manual login** in the Playwright-controlled
  browser profile; after that it persists across runs.
- **Airtable writes take field IDs, not names** — see the field ID map in
  `SKILL.md` if a write fails with an unrecognized-field error.
