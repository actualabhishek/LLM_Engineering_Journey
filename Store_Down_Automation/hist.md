# Build History (redacted for portfolio — real company/employee/system identifiers replaced with placeholders; timestamps and the sequence of events are real)

Chronological, date/time-stamped log kept the whole way through the build. Curated down from the full internal log to the entries that show the actual engineering decisions and corrections — nothing here is smoothed over after the fact, this is what happened when it happened.

---

## Planning session

Worked through the full multi-agent architecture before writing any code, per an explicit "produce the plan first" instruction. Landed on: a five-role architecture (a coordinator + four system-scoped agents), scheduled polling as the trigger (justified with a networking analogy — SNMP polling vs. traps, since no admin access exists to configure a push-based trigger), a full Pydantic hand-off schema set, and a phase-wise build plan gated on real-data validation at every step, not just code review.

## Phase 1 — incident detection, built and validated

Built the ticket-queue scan: regex-match a specific short-description pattern, extract the store code (confirmed against real data that the connecting words vary — "for store X" vs. "for X" vs. "store X" with no "for" at all — so the parser can't assume one fixed phrasing), check state, and scan the full activity history for any sign a human is already handling it.

**A real miss, caught and fixed**: the first version of the idempotency scan only checked the most recent ~15 of 64 activities on a real ticket and concluded no prior contact existed. It was wrong — a full human email thread was sitting further down the history. Fixed by requiring a genuine top-to-bottom scan, not a "looks quiet" heuristic. This is the kind of bug that only shows up against real data with real history depth, not a clean test fixture.

## Phase 2 — directory lookup, built and validated

Validated against several real store codes plus one deliberately invalid one, to confirm the "not found" path doesn't fabricate a match.

**A real fabrication risk, caught before it caused harm**: for one role with nobody currently assigned, the directory page displayed the literal text "No Match" in the exact position a real name normally appears — same styling, same layout. Without an explicit check, an agent would read that as if it were a person's actual name. Added a rule to recognize that string specifically and treat it as "nobody assigned," never as data.

## Phase 3 — email composition, a real blocker, then a real correction

Original design: a separate resolution step using the email platform's own address-book search to turn a name into an email. Tested live — real people, confirmed working addresses — and got "no results found," repeatedly. Redesigned around a different approach: the directory site itself reveals a contact card (with the real email) when you hover a person's photo. Confirmed against four different real people.

**Then found the actual root cause of the earlier "failure."** The browser had two different Microsoft accounts signed in — the real work account, and a stale session from an unrelated organization. The address-book test had silently run against the wrong tenant's directory the whole time. Retested on the correct account: the address-book search worked fine too. The lesson wasn't "which method works," it was "verify which account is active before trusting any result" — now a mandatory first step before any email action, every time.

Validated the full compose flow (recipients, subject, body) against real data, with zero real sends — including recovering cleanly from a genuine mid-test mistake where a misplaced click opened a second, unrelated compose window.

## Phase 4 — ticket close-out + logging, built and validated

Built the close-out flow (paste the sent email into the ticket, set it on hold) and the Airtable logging step. Live-validated the Airtable write path: wrote a row, upserted a second time with more fields, confirmed both writes landed on the same record rather than duplicating — the exact mechanism the pipeline relies on to resume correctly after an interruption instead of double-processing.

## Phase 5 — the coordinator, built and dry-run traced

Built the orchestrator: a schema validator every hand-off gets piped through, an idempotency check that resumes from a recorded phase instead of restarting, a kill switch, and a `send_mode` setting (supervised by default — every email needs an explicit go-ahead; autonomous only once trusted). Traced the full procedure against already-validated real data rather than a fresh live run, since the failure paths (not-found, resume-after-interruption) were already proven individually in earlier phases.

## Phase 6 — hardening

Added a documented "known flaky behavior" section to every agent, each one tied to something that actually broke during this build rather than a hypothetical: a natural-language element search occasionally matching the wrong control, screenshots timing out on slow page loads, scroll-position-dependent content getting misread as absent. Also worked out that neither of the two scheduling options available in this environment actually fits a pipeline that depends on a real, already-authenticated local browser session — a genuinely useful thing to learn early rather than build around blindly.
