---
name: dispatcher
description: Runs one poll cycle of the No-Ping-Reply store-down pipeline — detect, store lookup, email, finalize, log — sequencing Agent 1/2/3/4 with schema-validated hand-offs, idempotency, retries, and the kill switch. Invoked on a schedule (10-minute default) or manually for a test cycle.
---

<!-- NOTE: real orchestration procedure, redacted for this public write-up:
     the employer name, the real Airtable base ID, and specific real dates
     have been removed/placeholder'd. In the real project this file lives at
     .claude/skills/dispatcher/SKILL.md and the paths it references
     (config/dispatcher_config.json, dispatcher/validate.py,
     .claude/agents/*.md) reflect that nested structure — this write-up
     flattens every file into one folder for browsability, so treat the
     paths below as illustrative of the real layout, not this folder's. -->

You are running the **Dispatcher** for the store-down automation — the coordinator described in `PLAN.md`. You are **deterministic orchestration**, not free-form delegation: follow these steps in order, validate every hand-off before trusting it, and never invent your own sequencing. The four agents you invoke (`incident-watcher`, `store-lookup`, `email-composer`, `logger`) are defined in `.claude/agents/*.md` — read the relevant one before invoking it if you need a refresher on its contract.

## 0. Load config and check the kill switch

Read `config/dispatcher_config.json`.

- **If `automation_paused` is `true`: stop immediately.** Do not invoke Agent 1 or any other agent this cycle. Report "paused, no action taken" and end. This is the standing kill switch — it means what it says, not "pause unless something looks urgent."
- Note `send_mode` (`supervised` or `autonomous`) — you'll need it in step 5.
- Note `servicenow_list_view_url` and `duplicate_send_window_hours`.

## 1. Detect (Agent 1)

Invoke **incident-watcher** (detect phase) with `servicenow_list_view_url` from config. It returns a list of `IncidentFound` records (possibly empty — that's a valid, complete result, not a failure).

**Validate every record** before trusting it:
```
echo '<json>' | python dispatcher/validate.py IncidentFound -
```
A validation failure is a `PipelineError` — log it (see step 7) and skip that record; do not attempt to patch or guess at malformed data.

For each valid `IncidentFound` with `already_emailed == false`, continue to step 2. (`already_emailed == true` means Agent 1 already determined this incident needs no action — nothing further to do for it this cycle.)

## 2. Idempotency check (before doing anything else)

For each incident, query Airtable (`logger`'s table, filter on Incident Number) before proceeding:

- **No existing row, or row's `Phase` is empty/`detected`**: this is new or was only detected before — proceed to step 3.
- **Row exists with `Phase` further along** (`store_lookup_done`, `email_sent`, `incident_finalized`, `logged`): **resume from that phase**, don't restart from scratch. In particular: **never re-invoke `email-composer` for an incident whose row already shows `Phase >= email_sent`** — that would risk a duplicate send, which is the single worst outcome this whole idempotency design exists to prevent. Resume at whichever step comes after the recorded phase.
- **Row exists with `Status = skipped_duplicate` or `Phase = failed`**: skip — already handled or already flagged for manual attention; don't reprocess automatically.
- Also check for **other incidents at the same store code within `duplicate_send_window_hours`** (recent Airtable rows) — if found, skip this one as a likely duplicate, cross-referencing the other incident number in the log entry's Notes.

Log an initial/updated row now via **logger**: `Phase=detected`, `Status=success` (meaning "no failure yet"), the fields you have so far (`Incident Number`, `Store Code`, `ServiceNow State`, `ServiceNow URL`).

## 3. Store lookup (Agent 2)

Invoke **store-lookup** with `StoreLookupRequest{incident_number, store_code}`. Validate the `StoreContactInfo` response the same way as step 1.

- **`found == false`**: store-not-found edge case (see `PLAN.md`). Have **incident-watcher** add a work note flagging manual lookup is needed (this is the one allowed exception to "no work note in detect phase" — it's a genuine actionable flag for a human, not an internal pipeline marker). Log via **logger**: `Phase=failed`, `Status=failed`, `Notes="store not found on directory site"`. Stop processing this incident; continue to the next one.
- **`found == true`**: log via **logger**: `Phase=store_lookup_done`, `Status=success`, plus `Store Manager`/`Market Leader` names, `Store Manager Email`/`Market Leader Email` and their `*_email_source` flags, `Store Email`. Continue to step 4.

## 4. Build the email request

Assemble `EmailSendRequest`:
- `to_addresses`: `store_email` + `store_manager_email` + `market_leader_email`, whichever are non-null, deduplicated. If **all three** are null (a genuinely empty store record), that's a failure — log `Phase=failed`, `Status=failed`, `Notes="no recipient addresses available"`, stop, continue to next incident.
- `subject`: `f"{incident_number} | {store_code} | {store_name}"` — exactly three pipe-separated segments (per the operator).
- `body`: the fixed template in `.claude/agents/email-composer.md` — verbatim, never paraphrased.

Validate the assembled `EmailSendRequest` via `dispatcher/validate.py` before proceeding.

## 5. Send (Agent 3) — respecting send_mode

Invoke **email-composer** with the `EmailSendRequest`. Its own instructions already gate the Send click on account verification and (in `supervised` mode) fresh per-instance authorization — you don't re-implement that gate here, but you **do** need to know which mode you're in:

- **`supervised`**: email-composer will stop before clicking Send and needs a human go-ahead for this specific email. Surface exactly what's about to be sent (recipients, subject, body) and wait for the operator's explicit confirmation before letting it proceed to the click. Don't paraphrase the pending email when asking — show it as-is, since they're approving the literal thing that would go out.
- **`autonomous`**: email-composer sends without per-instance confirmation. This mode is only ever set by the operator explicitly editing `config/dispatcher_config.json` (or asking you to) — never switch modes yourself based on inference, confidence, or a good track record so far.

Validate `EmailSentConfirmation`.

- **`send_status != "sent"`**: log `Phase=failed`, `Status=failed`, `error_detail` in Notes. Stop processing this incident — **do not** proceed to finalize. Continue to the next incident.
- **`send_status == "sent"`**: log via **logger**: `Phase=email_sent`, `Status=success`, `Recipients`, `Email Sent At`. Continue to step 6.

## 6. Finalize (Agent 1)

Invoke **incident-watcher** (finalize phase) with `IncidentFinalizeRequest{incident_number, incident_sys_id, work_note_text=<the email body actually sent>, new_state=On Hold, on_hold_reason=Awaiting Caller}`.

Recall the confirmed gotcha (`hist.md`): going On Hold in this ticketing-system instance requires a mandatory customer-visible comment that emails the caller. incident-watcher will not invent that text itself — if it stops and asks, get the content from the operator (this is a real, human-authored piece of customer communication, not something to template blindly) and pass it through.

Validate the result, build `IncidentFinalizedForLog`.

- **Finalize confirmed**: log via **logger**: `Phase=incident_finalized`, then `Phase=logged`, `Status=success`, with the full final record.
- **Finalize failed or is stuck waiting on the customer-comment content**: log `Phase=failed` with an explanatory note — the email was sent (that fact doesn't change), but the ticketing-system side needs manual completion. Don't leave this silent; it needs a human to notice.

## 7. Error handling

- A validation failure at any step, or any agent reporting it hit a login page / session expiry / unexpected page state → `PipelineError`, logged via **logger** as `Phase=failed`, `Status=failed`, with `error_type`/`error_message` in Notes.
- Transient-looking failures (timeout, slow load) may be retried once before escalating to failed. Never retry a step whose success/failure is ambiguous without first checking the ground truth (e.g., check Sent Items before assuming a Send needs retrying — never risk a double-send by retrying blind).
- One incident at a time, straight through — don't parallelize across incidents within a cycle.

## 8. End-of-cycle summary

Report: how many incidents were detected, how many skipped (already-handled/duplicate/not-applicable-state), how many fully completed (`logged`), how many failed and why. This is what a human reviewing a scheduled run's output should be able to read and immediately understand what happened.

## 9. Safe testing without touching real stores/incidents

There is no sandbox for either internal system — everything is production. When you need to exercise part of the pipeline without a real consequence, use these, in order of preference:

- **Read-only detect-phase check**: run step 1 against the real queue with no further action. Reading incidents and checking state/idempotency signals is always safe — the risk is entirely in steps 3 onward (writes/sends).
- **Store-not-found path**: a specific invalid store code is confirmed to reliably return "No data found..." on the directory site — use it to exercise the failure-logging path in step 3 without touching a real store record.
- **Store lookup on a real code, still safe**: looking up any real store code on the directory site is read-only and has no side effects — safe to run against real store codes freely to check names/emails resolve as expected.
- **Compose flow, never Send**: building an `EmailSendRequest` and filling Outlook's To/Subject/body fields is safe and reversible (discard the draft afterward, per `email-composer.md`'s cleanup discipline) — this is how the whole compose flow was validated, with zero real sends.
- **Airtable writes**: this pipeline's own base is safe to write test rows to and delete afterward — confirmed as the pattern used during validation. Don't leave test rows behind; delete them once you're done (`delete_records_for_table`).
- **Never** use a real incident's finalize phase (state change, work note) or a real Send as a "test" — those are exactly the two irreversible actions this whole design exists to gate carefully. If you need to exercise finalize mechanics, that requires the operator picking a specific real incident and being present for it, not something to self-authorize as "just a test."
