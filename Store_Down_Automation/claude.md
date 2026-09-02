# claude.md

Multi-agent store-down incident automation (portfolio write-up — real client data redacted). Detects a specific ticket type on a ticketing system, resolves store contacts from an internal directory, sends a notification email, closes the ticket, and logs the transaction.

**Hard constraints (real, drove the whole design):** no API access to any of the three internal systems — browser automation only, against an already-authenticated session. Never fabricate data; a directory page can literally display "No Match" as if it were a name — must be recognized as no-data, not text. Verify which account is active before any email action — more than one can be signed into the same browser.

**Architecture:** four scoped subagents (watcher, directory-lookup, email-composer, logger) plus a deterministic Dispatcher coordinator — typed Pydantic hand-offs between every step, validated before trusting them. Kill switch and a `send_mode` (supervised/autonomous) gate the one irreversible action (sending email).

**Process:** every build session logged with a timestamp in `hist.md` (append-only); every prompt logged verbatim in `Prompt.md`. See `README.md` for the full write-up, including three real debugging stories from building this.
