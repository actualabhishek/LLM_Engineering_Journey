"""Unit tests for the pure state machine. No network, no clock - time is simulated."""
from app.monitor.state import DOWN, FLAPPING, UNKNOWN, UP, StateMachine, site_state


def make_sm(fail_threshold=3, recover_threshold=2, flap_max_changes=4, flap_window_s=600):
    return StateMachine(fail_threshold, recover_threshold, flap_max_changes, flap_window_s)


def test_normal_up_after_first_success():
    sm = make_sm()
    t = sm.evaluate("rtr01", ok=True, now=0)
    assert t is None  # 1 OK is below recover_threshold=2, still UNKNOWN
    t = sm.evaluate("rtr01", ok=True, now=10)
    assert t is not None
    assert (t.from_state, t.to_state) == (UNKNOWN, UP)


def test_single_drop_does_not_alert():
    sm = make_sm()
    sm.evaluate("rtr01", ok=True, now=0)
    sm.evaluate("rtr01", ok=True, now=10)  # UP
    t = sm.evaluate("rtr01", ok=False, now=20)  # 1 fail, threshold=3
    assert t is None
    assert sm.targets["rtr01"].state == UP
    t = sm.evaluate("rtr01", ok=True, now=30)  # recovers immediately, no real outage
    assert t is None
    assert sm.targets["rtr01"].state == UP


def test_sustained_outage_triggers_down_after_threshold():
    sm = make_sm(fail_threshold=3)
    sm.evaluate("rtr01", ok=True, now=0)
    sm.evaluate("rtr01", ok=True, now=10)  # UP
    assert sm.evaluate("rtr01", ok=False, now=20) is None
    assert sm.evaluate("rtr01", ok=False, now=30) is None
    t = sm.evaluate("rtr01", ok=False, now=40)  # 3rd consecutive fail
    assert t is not None
    assert (t.from_state, t.to_state) == (UP, DOWN)
    assert t.reason == "debounce"


def test_recovery_after_down():
    sm = make_sm(fail_threshold=3, recover_threshold=2)
    for now in (0, 10, 20, 30, 40):
        sm.evaluate("rtr01", ok=True if now <= 10 else False, now=now)
    assert sm.targets["rtr01"].state == DOWN

    assert sm.evaluate("rtr01", ok=True, now=50) is None  # 1st OK, recover_threshold=2
    t = sm.evaluate("rtr01", ok=True, now=60)  # 2nd OK
    assert t is not None
    assert (t.from_state, t.to_state) == (DOWN, UP)


def test_flapping_detected_after_too_many_changes_in_window():
    sm = make_sm(fail_threshold=1, recover_threshold=1, flap_max_changes=2, flap_window_s=100)
    # alternate ok/fail every 10s: each toggle is an immediate state change (thresholds=1).
    # The initial UNKNOWN -> DOWN establishment does not count as a flap change.
    t1 = sm.evaluate("rtr01", ok=False, now=0)  # UNKNOWN -> DOWN (not counted)
    assert t1.to_state == DOWN
    t2 = sm.evaluate("rtr01", ok=True, now=10)  # DOWN -> UP (change 1)
    assert t2.to_state == UP
    t3 = sm.evaluate("rtr01", ok=False, now=20)  # UP -> DOWN (change 2, not yet > max_changes=2)
    assert t3.to_state == DOWN
    t4 = sm.evaluate("rtr01", ok=True, now=30)  # DOWN -> UP (change 3, exceeds max_changes=2)
    assert t4.to_state == FLAPPING
    assert t4.reason == "flapping"
    assert sm.targets["rtr01"].state == FLAPPING


def test_flapping_clears_once_window_ages_out_and_state_stabilises():
    sm = make_sm(fail_threshold=1, recover_threshold=1, flap_max_changes=2, flap_window_s=50)
    sm.evaluate("rtr01", ok=False, now=0)
    sm.evaluate("rtr01", ok=True, now=10)
    sm.evaluate("rtr01", ok=False, now=20)
    sm.evaluate("rtr01", ok=True, now=30)  # -> FLAPPING
    assert sm.targets["rtr01"].state == FLAPPING
    # wait past the flap window so old change_times age out, then one more change is clean
    t = sm.evaluate("rtr01", ok=False, now=200)
    assert t is not None
    assert t.to_state == DOWN
    assert t.reason == "debounce"


def test_canary_failure_freezes_router_state():
    sm = make_sm(fail_threshold=3)
    sm.evaluate("rtr01", ok=True, now=0)
    sm.evaluate("rtr01", ok=True, now=10)  # UP
    # canaries down: even a FAIL result must not move the state or counters
    t = sm.evaluate("rtr01", ok=False, now=20, frozen=True)
    assert t is None
    assert sm.targets["rtr01"].state == UP
    assert sm.targets["rtr01"].consecutive_fail == 0


def test_both_routers_down_triggers_site_isolated():
    sm = make_sm(fail_threshold=1)
    sm.evaluate("rtr01", ok=False, now=0)
    sm.evaluate("rtr02", ok=False, now=0)
    states = {tid: ts.state for tid, ts in sm.targets.items()}
    assert states == {"rtr01": DOWN, "rtr02": DOWN}
    assert site_state(states) == "SITE_ISOLATED"


def test_site_state_none_when_only_one_down():
    states = {"rtr01": DOWN, "rtr02": UP}
    assert site_state(states) is None
