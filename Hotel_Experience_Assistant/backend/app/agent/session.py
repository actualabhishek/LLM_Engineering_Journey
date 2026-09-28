from dataclasses import dataclass


@dataclass
class PendingAction:
    tool: str
    args: dict


@dataclass
class AgentSession:
    guest_id: int | None = None
    pending_action: PendingAction | None = None
