---
description: Start/stop the Telegram-driven LinkedIn content pipeline, check its status, or manually trigger one topic through it
argument-hint: "[start|stop|status] | <topic text>"
---

# /postflow

Arguments: `$ARGUMENTS`

This command is a thin dispatcher. The full pipeline logic — research, drafting
via `/my-brand`, image generation, Airtable bookkeeping, Telegram approval,
and LinkedIn publishing — lives in
`skills/postflow-pipeline/SKILL.md` in this plugin. Read that file now and
keep it loaded as your working reference for everything below; do not
duplicate its logic here, follow it.

## Dispatch on `$ARGUMENTS`

**Empty, or `status`**
Run `node "${CLAUDE_PLUGIN_ROOT}/scripts/state.mjs" get` and report plainly:
whether the listener is active, the topic currently in flight (if any) and
its Status, and how many topics are queued behind it. If never configured,
say so and point at the "Setup" section of `SKILL.md`.

**`start`**
1. Run `node "${CLAUDE_PLUGIN_ROOT}/scripts/state.mjs" start`.
2. Confirm to the user: the pipeline is armed for the rest of *this* session.
   If this session was not launched with
   `--channels plugin:telegram@claude-plugins-official`, tell them inbound
   Telegram messages won't reach this session and they need to restart
   `claude` with that flag for the listener to actually receive topics.
3. From this point on, for the remainder of the session: treat every inbound
   message tagged `<channel source="telegram" ...>` per the rules in
   `SKILL.md` under "Handling inbound Telegram messages" — do this
   automatically, without the user re-invoking `/postflow` each time.

**`stop`**
1. Run `node "${CLAUDE_PLUGIN_ROOT}/scripts/state.mjs" stop`.
2. Confirm the listener is off. Inbound Telegram messages from now on should
   just get a short "postflow is stopped — send `/postflow start` to resume"
   style reply (if a chat_id is available to reply to), not be processed as
   topics. Do not touch any in-flight row silently — if `current` is
   non-null, mention what's still sitting in Airtable so the user knows it
   didn't get abandoned invisibly.

**Anything else — treat the full argument text as a topic**
This is the manual one-shot trigger for testing without sending a Telegram
message first. Run the full pipeline in `SKILL.md` starting at "Step 1 —
Research" for this topic, exactly as if it had arrived via Telegram — same
Airtable row, same Telegram research/approval messages, same queueing rules
if something is already in flight. The only difference from a real inbound
topic is how it was triggered. This does NOT require `start` to have been
run first, but if postflow is stopped, ask for confirmation before running
one topic through it anyway (they explicitly asked for this one, so proceed
if they confirm).
