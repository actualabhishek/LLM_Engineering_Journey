# PLAN.md — Store-Down Incident Automation (redacted for portfolio)

*Real company name, employee names/emails, store codes, ticket numbers, and system IDs have all been replaced with placeholders. The architecture, constraints, and schemas are exactly as built.*

## Context

A phase-wise, typed-schema, multi-agent system that automates a "no ping reply for `<store code>`" store-down runbook end-to-end: detect the ticket, look up the store's contacts on an internal directory site, email the Store Manager + Regional Lead + the store's shared mailbox, close the loop on the ticket, and log the transaction.

**Hard constraint:** no admin access and no API access exists or is obtainable for any of the three internal systems (ticketing, directory, email). Browser automation against the real web UI, driving an already-authenticated session, is the permanent implementation — not a placeholder for "the real integration later."

## 1. Architecture

Five roles, each owning exactly one system:

| Agent | Owns | Responsibility |
|---|---|---|
| **Dispatcher** (coordinator) | orchestration only | Runs the pipeline state machine, validates every hand-off against its Pydantic schema, enforces idempotency/dedup, retries, error routing, scheduling, kill-switch |
| **Agent 1 — incident_watcher** | Ticketing system | Detects matching tickets, checks state + "already contacted" (full activity-history scan, not a "looks quiet" heuristic), and later finalizes the ticket (pastes the sent email, sets it on hold) |
| **Agent 2 — store_lookup** | Internal directory | Looks up a store code, returns the store's shared mailbox + Store Manager's and Regional Lead's names **and real personal emails** — resolved via the directory page's own hover contact-card, with a documented fallback naming pattern when that doesn't surface a personal address |
| **Agent 3 — email_composer** | Email platform | Composes and sends the notification using addresses already resolved by Agent 2 — does no name/directory resolution of its own |
| **Agent 4 — logger** | Airtable | Persists pipeline state and the final transaction log — one row per incident, upserted as the pipeline progresses |

Agent 1 appears twice (detect, then finalize) because it's the same owned system, not the same step — the coordinator calls it at two different points in the state machine, the way a controller might touch the same device twice in one workflow without that device needing to know about the rest of the workflow.

**Why a coordinator, not free-form agent delegation:** the workflow is a fixed, linear pipeline with a strict hand-off contract at each step, not an open-ended reasoning task where agents should decide who talks to whom next. The Dispatcher is deterministic orchestration — it invokes each agent at a specific step and validates its output against the Pydantic model before advancing.

## 2. Trigger mechanism: scheduled polling

**Network analogy:** this is the SNMP-trap-vs-SNMP-poll choice. A trap (webhook) is lower latency but requires configuring the remote system to push to a listener you control — admin access on both ends, neither of which is available here. Polling needs neither: query the system on an interval you control. For a ticket queue where a few minutes of detection latency is immaterial, polling is the pragmatic, lowest-privilege choice.

## 3. The coordinator's responsibilities

- Owns the poll/schedule trigger and the pipeline state machine
- Validates every inter-agent payload against its Pydantic schema before passing it on
- Idempotency/dedup: before starting or resuming any phase, checks whether this incident (or this store, in a recent window) has already been handled
- Persists pipeline phase per incident so a crash mid-flow **resumes** at the correct step instead of restarting or double-sending
- Retry/backoff on transient failures; hard failures get routed to a `Failed` state with a human-readable reason
- Sequences one incident at a time — no concurrent browser sessions racing each other
- Owns a kill switch and a `send_mode` (supervised/autonomous) that only a human ever changes

## 4. Pydantic hand-off schemas (structure exactly as built)

```python
from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field


class IncidentState(str, Enum):
    NEW = "New"
    IN_PROGRESS = "In Progress"
    ON_HOLD = "On Hold"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class PipelinePhase(str, Enum):
    DETECTED = "detected"
    STORE_LOOKUP_DONE = "store_lookup_done"
    EMAIL_SENT = "email_sent"
    INCIDENT_FINALIZED = "incident_finalized"
    LOGGED = "logged"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    FAILED = "failed"


# Agent 1 (detect) -> Dispatcher
class IncidentFound(BaseModel):
    incident_number: str
    incident_sys_id: str
    short_description: str
    store_code: str = Field(pattern=r"^\d{3,5}$")
    state: IncidentState
    opened_at: datetime
    servicenow_url: str
    already_emailed: bool  # true if a full history scan found any prior contact signal


# Dispatcher -> Agent 2
class StoreLookupRequest(BaseModel):
    incident_number: str
    store_code: str


# Agent 2 -> Dispatcher — sole source of both names AND personal emails
class StoreContactInfo(BaseModel):
    incident_number: str
    store_code: str
    found: bool
    store_name: Optional[str] = None
    store_email: Optional[EmailStr] = None
    store_email_pattern_confirmed: bool = False
    store_manager_name: Optional[str] = None
    store_manager_email: Optional[EmailStr] = None
    store_manager_email_source: Optional[Literal["directory_hover", "pattern_derived"]] = None
    market_leader_name: Optional[str] = None
    market_leader_email: Optional[EmailStr] = None
    market_leader_email_source: Optional[Literal["directory_hover", "pattern_derived"]] = None
    lookup_source_url: str
    lookup_timestamp: datetime


# Dispatcher -> Agent 3 — addresses already resolved, no name lookup here
class EmailSendRequest(BaseModel):
    incident_number: str
    store_code: str
    to_addresses: list[EmailStr]  # store mailbox + manager + regional lead, whichever exist
    subject: str
    body: str


# Agent 3 -> Dispatcher
class EmailSentConfirmation(BaseModel):
    incident_number: str
    store_code: str
    to_addresses: list[EmailStr]
    subject: str
    body_sent: str
    sent_at: datetime
    send_status: Literal["sent", "failed"]
    error_detail: Optional[str] = None


# Dispatcher -> Agent 1 (finalize)
class IncidentFinalizeRequest(BaseModel):
    incident_number: str
    incident_sys_id: str
    work_note_text: str
    new_state: IncidentState = IncidentState.ON_HOLD
    on_hold_reason: str = "Awaiting Caller"


# Agent 1 (finalize) -> Dispatcher -> feeds Agent 4
class IncidentClosedForLog(BaseModel):
    incident_number: str
    store_code: str
    store_manager_name: Optional[str] = None
    market_leader_name: Optional[str] = None
    store_manager_email: Optional[EmailStr] = None
    market_leader_email: Optional[EmailStr] = None
    email_sent_at: datetime
    incident_state_after: IncidentState
    on_hold_reason: str
    servicenow_url: str


# Dispatcher -> Agent 4
class AirtableLogRecord(BaseModel):
    incident_number: str
    store_code: str
    store_manager_name: Optional[str] = None
    market_leader_name: Optional[str] = None
    recipients: list[EmailStr] = Field(default_factory=list)
    email_sent_at: Optional[datetime] = None
    servicenow_state: IncidentState
    servicenow_url: str
    logged_at: datetime
    phase: PipelinePhase
    status: Literal["success", "partial_failure", "failed", "skipped_duplicate"]
    notes: Optional[str] = None


# Any agent -> Dispatcher, on failure
class PipelineError(BaseModel):
    incident_number: Optional[str] = None
    phase: PipelinePhase
    agent: Literal["incident_watcher", "store_lookup", "email_composer", "logger"]
    error_type: str
    error_message: str
    occurred_at: datetime
    retry_count: int = 0
    recoverable: bool
```

## 5. Error handling & edge cases

| Case | Handling |
|---|---|
| Ticket state isn't New/In Progress | No action at all — normal, not an error |
| Store not found on the directory | `found=false`; flag the ticket for manual follow-up; log `Failed`, no fabricated data |
| Already contacted (found anywhere in a full history scan, not just the pipeline's own prior output) | Skip the whole pipeline for that incident |
| Directory reveals only the shared mailbox, not a personal address, for a person | Fall back to a confirmed naming pattern, flagged as `pattern_derived` rather than presented as page-confirmed |
| A directory role shows the literal text "no match" | Treated as no assignment, never as a real name |
| Email send fails or is unconfirmed | Never proceed to finalize; a pending/unsent email is never treated as done |
| Crash mid-pipeline | Resume from the last recorded phase in Airtable — never re-send an already-sent email |

## 6. Build phases

Each phase built one agent (or half of one), validated against real, read-mostly or test-safe data before the next began. No email send was ever validated by actually sending, even to a test mailbox — the compose flow was built and checked up to the point of Send; the send action itself is gated by an explicit mode a human controls. See `hist.md` for what was actually found and fixed at each phase.

1. Foundations — schemas, scaffolding
2. Agent 1 (detect half)
3. Agent 2 (directory lookup)
4. Agent 3 (email composer)
5. Agent 1 (finalize half) + Agent 4 (logger)
6. Dispatcher (orchestration)
7. Hardening — flaky-behavior documentation, safe-test-lane guidance

## 7. Implementation notes

- Each agent = a scoped subagent definition with least-privilege tool access matching its owned system
- The Dispatcher is deterministic orchestration — a fixed procedure, not a free-form multi-agent conversation
- No credentials stored; relies on a persistent, already-authenticated browser session — and always verifies *which* account is active before acting, since more than one can be signed in
- Testing strategy: unit-test schema validation with no browser needed → read-only integration test against the live site → supervised end-to-end test before any unattended operation

---

Part of the `llm-engineering-journey` portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.
