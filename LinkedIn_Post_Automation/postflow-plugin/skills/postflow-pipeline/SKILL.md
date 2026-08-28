---
name: postflow-pipeline
description: Full step-by-step logic for the /postflow LinkedIn content pipeline (research, draft via /my-brand, image generation, Airtable tracking, Telegram approval, LinkedIn publish via Playwright). Loaded and followed by the /postflow command; also consult it whenever an inbound Telegram message needs to be evaluated while the postflow listener is active.
version: 0.1.0
---

# postflow pipeline

This is the reference the `/postflow` command follows. It is not itself a
slash command — `/postflow` reads this file and executes it.

## Tool name conventions used below

- Telegram: tools are exposed by the connected `telegram` MCP plugin as
  `reply`, `react`, `edit_message`, `download_attachment`. The fully
  qualified name typically looks like `mcp__plugin_telegram_telegram__reply`.
  If a call by that name fails as unknown, run
  `ToolSearch({query: "select:mcp__plugin_telegram_telegram__reply,mcp__plugin_telegram_telegram__react,mcp__plugin_telegram_telegram__edit_message,mcp__plugin_telegram_telegram__download_attachment"})`
  first — these are deferred tools and must be loaded before use. If that
  exact name isn't found, `ToolSearch({query: "telegram reply react"})` to
  locate the real name.
- Playwright: `mcp__plugin_playwright_playwright__browser_*` (navigate,
  click, type, snapshot, file_upload, wait_for, evaluate, find,
  take_screenshot). Load via ToolSearch the same way if deferred.
- Airtable: `mcp__claude_ai_Airtable__*` (list_records_for_table,
  create_records_for_table, update_records_for_table, get_table_schema).
- **Telegram has no inline-keyboard / button tool and no callback-query
  channel back to this session.** Approval is done by plain-text reply
  (see Step 4/5). Do not attempt to construct a `reply_markup` argument —
  the `reply` tool does not accept one.

## Setup (do this the first time /postflow is used; skip if already done)

Required environment (from `.env` in the plugin root, or real env vars):

| Var | Purpose |
|---|---|
| `AIRTABLE_BASE_ID` | `app2FBJB0YQw5GcV4` ("LinkedIn PostFlow" base) unless the user repointed it |
| `AIRTABLE_TABLE_ID` | `tblJS8x1EWQHp5ZvY` (the "Posts" table) |
| `OPENROUTER_API_KEY` | OpenRouter API key (image gen routes through OpenRouter's Image API, not the direct Gemini API — the direct API's free tier has zero image quota) |
| `OPENROUTER_IMAGE_MODEL` | defaults to `google/gemini-2.5-flash-image` |
| `CLOUDINARY_URL` or `CLOUDINARY_CLOUD_NAME`/`CLOUDINARY_API_KEY`/`CLOUDINARY_API_SECRET` | image hosting |

If any required var is missing when a step needs it, tell the user exactly
which one via Telegram (if you have a chat_id) or in the terminal, and stop
that run rather than guessing or hardcoding a placeholder. Copy
`.env.example` to `.env` if `.env` doesn't exist yet, and remind the user to
fill it in.

### Airtable field ID map (base `app2FBJB0YQw5GcV4`, table `tblJS8x1EWQHp5ZvY`)

Airtable's write tools take field **IDs**, not names. Use this map; if a
write ever fails with an unrecognized-field error, call
`list_tables_for_base` again to re-resolve (the user may have edited the
base) and update your working memory of this map for the rest of the
session.

| Field | ID | Type |
|---|---|---|
| Topic | `fldmurT4Y9iT9Bn7K` | singleLineText (primary) |
| Status | `fldCSEjKiPqn2jxwj` | singleSelect: Researching, Drafted, Awaiting Approval, Approved, Rejected, Posted, Failed |
| Research Summary | `flddIXb6dqOoh3JeE` | multilineText |
| Draft Post | `fld78Svpu7U4xR0Dq` | multilineText |
| Image Prompt | `fldhtYq3wvdxm7A1I` | multilineText |
| Image URL | `fldmf39krIhlkKORQ` | url |
| Telegram Chat ID | `fldIxSesnDwAX6Tqg` | singleLineText |
| Telegram Message ID | `fldeIn1O5Tf9DdGsH` | singleLineText |
| LinkedIn Post URL | `fldOxuNH7MipVSiit` | url |
| Posted At | `fldmBlOUlCTKKktlh` | dateTime |
| Error | `fld7rqI3XvTU5O6Y0` | multilineText |
| Created At | `fldbbSGmnsRabHiwD` | dateTime |

### State store

`scripts/state.mjs` (in this plugin) holds listener on/off, the run
currently in flight, and the queue of topics waiting behind it. Always use
it instead of hand-tracking this in your own memory — it's what lets
`/postflow status`, a later turn, or even a fresh session pick up where
things left off.

```
node "${CLAUDE_PLUGIN_ROOT}/scripts/state.mjs" get
node "${CLAUDE_PLUGIN_ROOT}/scripts/state.mjs" start
node "${CLAUDE_PLUGIN_ROOT}/scripts/state.mjs" stop
node "${CLAUDE_PLUGIN_ROOT}/scripts/state.mjs" set-current '{"recordId":"rec...","topic":"...","chatId":"...","messageId":null}'
node "${CLAUDE_PLUGIN_ROOT}/scripts/state.mjs" clear-current
node "${CLAUDE_PLUGIN_ROOT}/scripts/state.mjs" enqueue '{"topic":"...","chatId":"..."}'
node "${CLAUDE_PLUGIN_ROOT}/scripts/state.mjs" dequeue
```

## Handling inbound Telegram messages

Once `/postflow start` has run, apply this for the rest of the session to
every message that arrives tagged `<channel source="telegram" chat_id="..."
message_id="..." ...>`. This only happens automatically while this Claude
Code session is alive, launched with
`--channels plugin:telegram@claude-plugins-official`, and `/postflow start`
has been run in it — there is no separate always-on background daemon (see
"Use" in the plugin README).

A new topic is only ever recognized by an explicit `Topic:` prefix (case
insensitive, optional space after the colon) — e.g. `Topic: agentic coding
in 2026`. This is deliberate: without a required prefix, any stray message
(small talk, a typo, someone else's forward) would silently get treated as a
LinkedIn post topic and start burning API calls. Trim the text after the
colon for the actual topic string; if it's empty, reply "Send it as `Topic:
<what you want the post about>`." and do nothing else.

1. Read state: `node scripts/state.mjs get`.
2. If `active` is false: this shouldn't normally happen (start turns it on),
   but if it does, send a short reply — "postflow is stopped — send
   `/postflow start` to resume" — and do nothing else.
3. If `active` is true and `current` is **not** null: this is either a
   decision on the in-flight row or a new topic to queue.
   - Trim and case-fold the text. If it starts with `approve` → go to
     **Step 5a (Approve)** below using `current`.
   - If it starts with `reject` → go to **Step 5b (Reject)** below using
     `current`.
   - If it starts with `topic:` (case insensitive): run `enqueue` with
     `{"topic": <text after the colon>, "chatId": <chat_id>}`, and reply:
     "📥 Queued — I'll research this once the current post
     (\"<current.topic>\") is resolved."
   - Otherwise: reply "Reply APPROVE or REJECT for the current draft, or
     send \"Topic: <text>\" to queue a new one." and do nothing else — don't
     guess at intent.
4. If `active` is true and `current` **is** null:
   - If the message starts with `topic:` (case insensitive): this is a
     fresh topic. Go to **Step 1 — Research** with the text after the colon
     as the topic, and this chat_id.
   - Otherwise: reply "Send \"Topic: <what you want the post about>\" to
     start one." and do nothing else.

## Step 1 — Research

1. Reply immediately: `🔎 Researching: <topic>`.
2. Create the Airtable row now (`create_records_for_table`) with Topic set
   and Status = "Researching". Capture the returned record id.
3. Set state: `set-current` with `{recordId, topic, chatId, messageId: null}`.
4. Run WebSearch 3-6 times covering: what's new/changed recently, concrete
   stats or data points, credible primary sources, and news from the last
   30 days on the topic. Load WebSearch via ToolSearch first if it's
   deferred. Prioritize primary sources (vendor docs, standards bodies,
   original reporting) over aggregator blogs.
5. Write a 150-300 word bullet-point research summary — the developments,
   the data points, and the sources you'd cite — into the "Research
   Summary" field. Set Status = "Drafted" once written (this table doesn't
   have a separate "research done" status; "Drafted" here means "research
   is in and ready to draft from" — you'll overwrite nothing by drafting
   next).

## Step 2 — Write the post (delegates to /my-brand)

Do **not** reinvent Abhishek's voice here and do not modify the `/my-brand`
command file. Instead:

1. Read `~/.claude/commands/my-brand.md` (or wherever it resolves — it's a
   user-level command) to load its voice instructions.
2. Apply those instructions yourself to draft the LinkedIn post, exactly as
   if the user had run `/my-brand <research summary + spec>`. The
   "task/text" input is: the research summary from Step 1, plus this
   explicit spec appended:
   - LinkedIn post, 1200-1600 characters (count it — if outside range,
     revise and recount, up to 2 revision passes)
   - hook-first opening line
   - short, punchy paragraphs (no dense blocks)
   - 3-5 relevant hashtags at the end, no more
   - no em-dashes anywhere (—) — if one slips in, replace it with a period,
     comma, or rewrite the clause
   - grounded in the research summary's actual facts/sources, not generic
     AI hype
3. Save the final text into "Draft Post". Status stays "Drafted".

## Step 3 — Generate the image

1. Derive an image prompt from the topic and the post's angle — a visual
   metaphor, not literal text-in-image, unless a clean short text overlay
   is genuinely the right call for this specific post. Write 1-3 sentences
   describing composition, style, mood.
2. Generate:
   `node "${CLAUDE_PLUGIN_ROOT}/scripts/generate_image.mjs" "<prompt>" "${CLAUDE_PLUGIN_ROOT}/state/images/<recordId>.png"`
   (create the `state/images/` dir first if needed). This calls a Gemini
   image model via OpenRouter's Image API and writes the PNG locally; it
   prints the file path on success.
3. Upload it so Airtable and LinkedIn both have a URL:
   `node "${CLAUDE_PLUGIN_ROOT}/scripts/upload_cloudinary.mjs" "<local png path>"`
   — prints the `secure_url` on success. Keep the **local file path** too;
   you need it again in Step 6 for the LinkedIn upload (Playwright needs a
   local file, not a URL).
4. Update the Airtable row: Image Prompt = the prompt text, Image URL = the
   Cloudinary URL.
5. If either script fails (missing/invalid API key, network error, etc.):
   set Status = "Failed", write the error into "Error", tell the user on
   Telegram what broke and which env var to check, `clear-current`, then
   check the queue (`dequeue`) and start the next topic if one is waiting.
   Do not retry image generation silently more than once.

## Step 4 — Send for approval

1. Send one Telegram message via `reply`, with the local image file
   attached (`files: [<local png path>]`) and text along these lines:

   ```
   📝 Draft ready — "<topic>"

   <draft post text>

   ---
   Reply APPROVE to publish this to LinkedIn, or REJECT to discard it.
   ```

   (No inline keyboard — see the tool-name note at the top of this file for
   why. Plain text reply is the approval mechanism.)
2. Capture the returned message id. Update Airtable: Telegram Chat ID,
   Telegram Message ID, Status = "Awaiting Approval".
3. Update state: `set-current` with the messageId filled in.
4. Stop here. Do not proceed further in this turn — wait for the next
   inbound Telegram message, which "Handling inbound Telegram messages"
   above will route back to Step 5a/5b.

## Step 5a — Approve

1. Update Airtable: Status = "Approved".
2. Reply on Telegram: `✅ Approved — publishing to LinkedIn now...`
3. Go to **Step 6 — Publish to LinkedIn**.

## Step 5b — Reject

1. Update Airtable: Status = "Rejected".
2. Reply on Telegram: `❌ Rejected — discarded. Send a new topic anytime.`
3. `clear-current`, then `dequeue` — if a topic was waiting, start
   **Step 1 — Research** for it immediately (reply "🔎 Researching: ..."
   for that one too, per the queueing rule).
4. Stop. No auto-retry, no auto-revision — that only happens if the user
   sends a new topic or explicitly asks for a revision.

## Step 6 — Publish to LinkedIn (Playwright)

1. Navigate to `https://www.linkedin.com/feed/`.
2. Take a snapshot. If you land on a login page (or see a "Sign in"
   control instead of a feed/compose control), the persisted session isn't
   logged in: reply on Telegram
   `⚠️ LinkedIn isn't logged in in the automated browser — please log in
   there manually, then reply CONTINUE.` Wait for `CONTINUE` before
   retrying this step. Do this at most once per run; if it's still not
   logged in after that, treat it as a publish failure (see step 5 below).
3. Click "Start a post" (or equivalent compose entry point). Type the
   approved Draft Post text into the post editor.
4. Add the image: use the post composer's photo/media control, then
   `browser_file_upload` with the **local** PNG path from Step 3.
   Wait for the image to finish uploading/processing before continuing.
5. Click "Post". Wait for the post to complete (composer closes / a
   confirmation appears).
6. Try to capture the published post's URL: check the feed for the new
   post and its permalink/timestamp link, or the user's activity page.
   This is best-effort — LinkedIn doesn't always expose it immediately. If
   you can't get a reliable URL after a reasonable attempt, proceed without
   one rather than blocking.
7. **On success:** update Airtable — Status = "Posted", Posted At = now
   (ISO 8601), LinkedIn Post URL = the URL if you got one. `clear-current`.
   Reply on Telegram: `🎉 Posted!` plus the link if you have one (or "link
   not captured, check LinkedIn" if not).
8. **On failure at any point in this step:** retry the whole step **once**.
   If it fails again: Status = "Failed", Error = a concise description of
   what broke (the actual error text, not a guess), `clear-current`, and
   reply on Telegram: `⚠️ Publishing failed: <short reason>. Draft is
   safe in Airtable — see it and retry manually if needed.` Do not attempt
   a third try.
9. Either way (success or final failure), `dequeue` — if a topic is
   waiting, start **Step 1 — Research** for it.

## Cross-cutting rules

- One Airtable row per topic, updated in place start to finish — never
  create a second row for the same run. The row is created once, in Step 1.
- Every Telegram message you send is short: one status emoji + one line,
  plus content only where the step calls for it (the draft, the failure
  reason, etc).
- Only one topic is ever "in flight" (Researching through Awaiting
  Approval/publishing) at a time; everything else waits in `queue` and is
  processed strictly in order, one at a time — never interleave two runs'
  Telegram messages.
- Never fabricate a research fact, a source, an image URL, or a LinkedIn
  post URL. If something can't be obtained, say so plainly instead of
  guessing.
