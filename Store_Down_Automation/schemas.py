"""
Typed hand-off contracts for the store-down incident automation.

Every inter-agent hand-off in this system passes one of these Pydantic models,
never a raw string or dict. See PLAN.md for the full design rationale.

NOTE: this is the real schema file from the project, unmodified in structure —
only the illustrative example values in comments (emails, domains) have been
replaced with placeholders for this public write-up.
"""

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


# Agent 1 (incident_watcher) -> Dispatcher (detect phase)
class IncidentFound(BaseModel):
    incident_number: str  # e.g. INC0000001
    incident_sys_id: str  # ticketing-system internal ID, for direct-URL re-navigation
    short_description: str
    store_code: str = Field(pattern=r"^\d{3,5}$")
    state: IncidentState
    opened_at: datetime
    servicenow_url: str
    already_emailed: bool  # true if a full history scan found any prior email correspondence signal


# Dispatcher -> Agent 2 (store_lookup)
class StoreLookupRequest(BaseModel):
    incident_number: str
    store_code: str


# Agent 2 (store_lookup) -> Dispatcher
# Agent 2 is the sole source of both names AND personal emails for the Store
# Manager / Market Leader — hovering their photo/name card on the internal
# directory site reveals a "Live Persona"-style contact card with a real email
# in most cases (confirmed live against several real people, all matching an
# "initial[.]lastname@company.com" pattern). When hover instead reveals only
# the store's generic mailbox (seen for one real Store Manager), fall back to
# constructing the pattern address and flag it as unconfirmed via the
# *_email_source field — never silently treat a pattern guess as equivalent
# to a page-confirmed address.
class StoreContactInfo(BaseModel):
    incident_number: str
    store_code: str
    found: bool  # false => store-not-found error path, nothing below is populated
    store_name: Optional[str] = None
    store_email: Optional[EmailStr] = None
    store_email_pattern_confirmed: bool = False  # False if <code>mgr@company.com was assumed, not read off the page
    store_manager_name: Optional[str] = None
    store_manager_email: Optional[EmailStr] = None
    store_manager_email_source: Optional[Literal["directory_hover", "pattern_derived"]] = None
    market_leader_name: Optional[str] = None
    market_leader_email: Optional[EmailStr] = None
    market_leader_email_source: Optional[Literal["directory_hover", "pattern_derived"]] = None
    lookup_source_url: str
    lookup_timestamp: datetime


# Dispatcher -> Agent 3 (email_composer)
# All addresses are already resolved by Agent 2 — Agent 3 does no name
# resolution of its own. (The email platform's own directory search actually
# works fine too, confirmed once tested on the correct work account — an
# earlier test on a different, wrongly-active account falsely suggested it
# didn't. Resolution stays in Agent 2 by design, not because that search is
# unreliable.)
class EmailSendRequest(BaseModel):
    incident_number: str
    store_code: str
    to_addresses: list[EmailStr]  # store_email + store_manager_email + market_leader_email, whichever exist
    subject: str
    body: str


# Agent 3 (email_composer) -> Dispatcher
class EmailSentConfirmation(BaseModel):
    incident_number: str
    store_code: str
    to_addresses: list[EmailStr]  # the addresses the message actually went to
    subject: str
    body_sent: str
    sent_at: datetime
    send_status: Literal["sent", "failed"]
    error_detail: Optional[str] = None


# Dispatcher -> Agent 1 (incident_watcher) (finalize phase)
class IncidentFinalizeRequest(BaseModel):
    incident_number: str
    incident_sys_id: str
    work_note_text: str  # the sent email content, pasted verbatim
    new_state: IncidentState = IncidentState.ON_HOLD
    on_hold_reason: str = "Awaiting Caller"


# Agent 1 (incident_watcher) -> Dispatcher (finalize confirmation) -> feeds Agent 4
class IncidentFinalizedForLog(BaseModel):
    incident_number: str
    store_code: str
    store_manager_name: Optional[str] = None
    market_leader_name: Optional[str] = None
    store_manager_email: Optional[EmailStr] = None  # sourced from Agent 2's directory-hover lookup
    market_leader_email: Optional[EmailStr] = None  # sourced from Agent 2's directory-hover lookup
    email_sent_at: datetime
    incident_state_after: IncidentState
    on_hold_reason: str
    servicenow_url: str


# Dispatcher -> Agent 4 (logger)
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
