"""Pure UP/DOWN/FLAPPING state machine, plus site-level aggregation.

No network, DB, or clock calls in this file (CLAUDE.md rule 1). Time and the
canary-freeze flag are passed in by the caller so this is fully unit-testable
with a fake prober and simulated timestamps.
"""
from __future__ import annotations

from dataclasses import dataclass, field

UNKNOWN = "UNKNOWN"
UP = "UP"
DOWN = "DOWN"
FLAPPING = "FLAPPING"
SITE_ISOLATED = "SITE_ISOLATED"


@dataclass
class Transition:
    target_id: str
    from_state: str
    to_state: str
    ts: float
    reason: str  # "debounce" or "flapping"


@dataclass
class TargetState:
    target_id: str
    state: str = UNKNOWN
    consecutive_ok: int = 0
    consecutive_fail: int = 0
    last_change_ts: float | None = None
    change_times: list[float] = field(default_factory=list)  # UP<->DOWN transitions, for flap detection


class StateMachine:
    """Tracks all targets. Call evaluate() once per target per probe cycle."""

    def __init__(
        self, fail_threshold: int, recover_threshold: int, flap_max_changes: int, flap_window_s: int
    ) -> None:
        self.fail_threshold = fail_threshold
        self.recover_threshold = recover_threshold
        self.flap_max_changes = flap_max_changes
        self.flap_window_s = flap_window_s
        self.targets: dict[str, TargetState] = {}

    def _get(self, target_id: str) -> TargetState:
        if target_id not in self.targets:
            self.targets[target_id] = TargetState(target_id=target_id)
        return self.targets[target_id]

    def evaluate(self, target_id: str, ok: bool, now: float, frozen: bool = False) -> Transition | None:
        """Feeds one probe result. Returns a Transition if the target's state changed, else None.

        frozen=True means canaries are down (monitor's own internet is out): counters are
        not updated and no transition can happen (CLAUDE.md rule 3 - freeze router state).
        """
        if frozen:
            return None

        ts = self._get(target_id)

        if ok:
            ts.consecutive_ok += 1
            ts.consecutive_fail = 0
        else:
            ts.consecutive_fail += 1
            ts.consecutive_ok = 0

        new_state = self._next_state(ts)
        if new_state == ts.state:
            return None

        if ts.state in (UP, DOWN) and new_state in (UP, DOWN):
            ts.change_times.append(now)
        ts.change_times = [t for t in ts.change_times if now - t <= self.flap_window_s]

        reason = "debounce"
        if len(ts.change_times) > self.flap_max_changes:
            new_state = FLAPPING
            reason = "flapping"

        transition = Transition(target_id=target_id, from_state=ts.state, to_state=new_state, ts=now, reason=reason)
        ts.state = new_state
        ts.last_change_ts = now
        return transition

    def _next_state(self, ts: TargetState) -> str:
        if ts.state in (UNKNOWN, DOWN, FLAPPING) and ts.consecutive_ok >= self.recover_threshold:
            return UP
        if ts.state in (UNKNOWN, UP, FLAPPING) and ts.consecutive_fail >= self.fail_threshold:
            return DOWN
        return ts.state


def site_state(states: dict[str, str]) -> str | None:
    """Returns SITE_ISOLATED if every known target is DOWN, else None (no site-level override)."""
    if states and all(s == DOWN for s in states.values()):
        return SITE_ISOLATED
    return None
