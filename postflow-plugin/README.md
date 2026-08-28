# postflow

Telegram-driven LinkedIn content pipeline: send a topic to your Telegram
bot, it researches it, drafts a post in your `/my-brand` voice, generates an
image, sends both back for approval, and publishes to LinkedIn on approval.

## Requires

Already-installed/connected, not bundled with this plugin:

- `telegram@claude-plugins-official` — configured via `/telegram:configure`
  and paired via `/telegram:access` (see that plugin's own README).
- `playwright@claude-plugins-official` — used to publish to LinkedIn.
- The Airtable MCP connector (`claude.ai` connector, not a marketplace
  plugin) — used for the `Posts` tracking table.
- Your existing `~/.claude/commands/my-brand.md` command — read, never
  modified, for the writing step.

## Install

From a `claude` session in this project (or point `--plugin-dir` at
`postflow-plugin/` directly for local dev without installing):

```
/plugin marketplace add F:\claude_code_VS\LinkedIn_Post_Automation\.claude-plugin\marketplace.json
/plugin install postflow@postflow-local
```

## Configure

1. Copy `postflow-plugin/.env.example` to `postflow-plugin/.env` and fill in:
   - `OPENROUTER_API_KEY` — https://openrouter.ai/settings/keys. Image
     generation routes through OpenRouter's Image API to a Gemini image
     model (`google/gemini-2.5-flash-image` by default) rather than the
     direct Gemini API, whose free tier has zero quota for image output —
     OpenRouter bills per image on its own account instead.
   - `CLOUDINARY_URL` (or the three separate `CLOUDINARY_*` vars) —
     https://cloudinary.com, free tier is fine. Used to host the generated
     image at a URL Airtable and LinkedIn can both use.
   - `AIRTABLE_BASE_ID` / `AIRTABLE_TABLE_ID` — already pointed at the
     "LinkedIn PostFlow" base created for this plugin; change only if you
     move to a different base.
2. Make sure Telegram is configured and you're paired
   (`/telegram:configure`, `/telegram:access`).
3. First LinkedIn publish will need a manual login: Playwright's default
   profile persists across runs, so you only do this once. If Step 6 of
   the pipeline reports LinkedIn isn't logged in, log in in the automated
   browser window when it opens, then reply `CONTINUE` on Telegram.

## Use

```
/postflow start     # arm the listener for this session
/postflow stop       # disarm it
/postflow status      # (or bare /postflow) — what's in flight, what's queued
/postflow <topic>    # manual one-shot trigger, no Telegram message needed
```

`start` only takes effect for the Claude Code session it's run in, and only
receives Telegram messages if that session was launched with:

```
claude --channels plugin:telegram@claude-plugins-official
```

There's no separate background daemon — the "listener" is this session
staying open and connected to the Telegram channel, per how Claude Code
channels work.

## Why approval is a text reply, not a button

The Telegram plugin exposes `reply`/`react`/`edit_message`/
`download_attachment` to the assistant, with no tool to send an inline
keyboard and no way for a button tap to reach the session — its
callback-query handling is internal to the plugin (pairing/permission
prompts only). So `/postflow` asks you to reply `APPROVE` or `REJECT` in
plain text instead. This was a deliberate tradeoff over patching the
installed telegram plugin's server code, which would silently break on the
plugin's next update.

## Files

- `commands/postflow.md` — the `/postflow` command (thin dispatcher).
- `skills/postflow-pipeline/SKILL.md` — the actual step-by-step pipeline
  logic; read this to see exactly what each step does.
- `scripts/generate_image.mjs` — calls the Gemini API image model.
- `scripts/upload_cloudinary.mjs` — uploads an image, returns a hosted URL.
- `scripts/state.mjs` — tiny state store: listener on/off, in-flight run,
  queue of topics waiting behind it.
- `state/` — created at runtime (state.json, generated images). Not
  committed.
