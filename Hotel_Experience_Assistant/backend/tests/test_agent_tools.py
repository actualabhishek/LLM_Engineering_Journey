from datetime import date, timedelta

from sqlalchemy import select

from app.agent.session import AgentSession, PendingAction
from app.agent.tools import (
    cancel_booking,
    check_availability,
    check_in,
    create_booking,
    enroll_loyalty,
    find_booking,
    loyalty_status,
    modify_booking,
    redeem_points,
    save_preferences,
)
from app.models import Booking, BookingStatus, Guest, Inventory, LoyaltyAccount, RoomType
from app.services import booking as booking_service
from app.services import loyalty as loyalty_service

TODAY = date.today()


def _room_type(db, code):
    return db.scalar(select(RoomType).where(RoomType.code == code))


def _inventory_row(db, room_type_id, day):
    return db.scalar(select(Inventory).where(Inventory.room_type_id == room_type_id, Inventory.date == day))


def _make_guest(db, first_name, last_name):
    guest = Guest(first_name=first_name, last_name=last_name)
    db.add(guest)
    db.commit()
    db.refresh(guest)
    return guest


def _asha(db):
    return db.scalar(select(Guest).where(Guest.last_name == "Rao"))


def _asha_booking(db):
    return db.scalar(select(Booking).where(Booking.guest_id == _asha(db).id))


def _asha_loyalty(db):
    return db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.guest_id == _asha(db).id))


# ---------------------------------------------------------------------------
# propose / confirm lifecycle (create_booking as the representative case)
# ---------------------------------------------------------------------------


def test_propose_create_booking_returns_summary_and_does_not_mutate_db(seeded_db):
    session = AgentSession()
    check_in_d, check_out_d = (TODAY + timedelta(days=20)).isoformat(), (TODAY + timedelta(days=22)).isoformat()
    room_type = _room_type(seeded_db, "deluxe")
    before_row = _inventory_row(seeded_db, room_type.id, TODAY + timedelta(days=20))
    before_booked = before_row.rooms_booked
    before_guest_count = seeded_db.query(Guest).count()
    before_booking_count = seeded_db.query(Booking).count()

    result = create_booking(
        seeded_db, session, "deluxe", check_in_d, check_out_d, 2, first_name="New", last_name="Guest"
    )

    assert "summary" in result
    assert session.pending_action == PendingAction(
        tool="create_booking",
        args=dict(
            room_type_code="deluxe",
            check_in=check_in_d,
            check_out=check_out_d,
            num_guests=2,
            special_requests=None,
            first_name="New",
            last_name="Guest",
        ),
    )
    seeded_db.expire_all()
    assert _inventory_row(seeded_db, room_type.id, TODAY + timedelta(days=20)).rooms_booked == before_booked
    assert seeded_db.query(Guest).count() == before_guest_count
    assert seeded_db.query(Booking).count() == before_booking_count


def test_confirm_create_booking_exact_match_executes_and_clears_pending(seeded_db):
    session = AgentSession()
    check_in_d, check_out_d = (TODAY + timedelta(days=20)).isoformat(), (TODAY + timedelta(days=22)).isoformat()
    args = dict(
        room_type_code="deluxe",
        check_in=check_in_d,
        check_out=check_out_d,
        num_guests=2,
        first_name="New",
        last_name="Guest",
    )

    create_booking(seeded_db, session, **args)
    result = create_booking(seeded_db, session, **args)

    assert session.pending_action is None
    assert result["reference"]
    assert result["status"] == "confirmed"
    booking = seeded_db.scalar(select(Booking).where(Booking.reference == result["reference"]))
    assert booking is not None
    assert session.guest_id == booking.guest_id


def test_confirm_with_different_args_reproposes_without_mutating(seeded_db):
    session = AgentSession()
    check_in_d, check_out_d = (TODAY + timedelta(days=20)).isoformat(), (TODAY + timedelta(days=22)).isoformat()
    other_check_out = (TODAY + timedelta(days=23)).isoformat()

    first = create_booking(
        seeded_db, session, "deluxe", check_in_d, check_out_d, 2, first_name="New", last_name="Guest"
    )
    before_booking_count = seeded_db.query(Booking).count()

    second = create_booking(
        seeded_db, session, "deluxe", check_in_d, other_check_out, 2, first_name="New", last_name="Guest"
    )

    assert "summary" in second
    assert session.pending_action.args["check_out"] == other_check_out
    assert seeded_db.query(Booking).count() == before_booking_count
    assert first != second


# ---------------------------------------------------------------------------
# error paths surface as {"error": ...}, not exceptions
# ---------------------------------------------------------------------------


def test_create_booking_unknown_room_type_error(seeded_db):
    session = AgentSession()
    ci, co = (TODAY + timedelta(days=1)).isoformat(), (TODAY + timedelta(days=2)).isoformat()

    result = create_booking(seeded_db, session, "bogus_room", ci, co, 1, first_name="A", last_name="B")

    assert "error" in result
    assert session.pending_action is None


def test_create_booking_no_availability_error(seeded_db):
    session = AgentSession()
    ci, co = TODAY + timedelta(days=30), TODAY + timedelta(days=31)
    guest_a = _make_guest(seeded_db, "A", "One")
    guest_b = _make_guest(seeded_db, "B", "Two")
    booking_service.create_booking(seeded_db, guest_a.id, "presidential_suite", ci, co, 1)
    booking_service.create_booking(seeded_db, guest_b.id, "presidential_suite", ci, co, 1)

    result = create_booking(
        seeded_db, session, "presidential_suite", ci.isoformat(), co.isoformat(), 1, first_name="C", last_name="Three"
    )

    assert "error" in result
    assert session.pending_action is None


def test_modify_booking_not_found_error(seeded_db):
    session = AgentSession()

    result = modify_booking(seeded_db, session, "ZZZZZZ", "Nobody", check_in=(TODAY + timedelta(days=1)).isoformat())

    assert "error" in result
    assert session.pending_action is None


def test_cancel_booking_wrong_last_name_error(seeded_db):
    session = AgentSession()
    booking = _asha_booking(seeded_db)

    result = cancel_booking(seeded_db, session, booking.reference, "WrongName")

    assert "error" in result
    assert session.pending_action is None
    seeded_db.refresh(booking)
    assert booking.status == BookingStatus.CONFIRMED


def test_enroll_loyalty_already_enrolled_error(seeded_db):
    session = AgentSession(guest_id=_asha(seeded_db).id)

    enroll_loyalty(seeded_db, session)
    result = enroll_loyalty(seeded_db, session)

    assert "error" in result
    assert session.pending_action is None


def test_redeem_points_insufficient_balance_error(seeded_db):
    session = AgentSession()
    account = _asha_loyalty(seeded_db)
    guest = _asha(seeded_db)

    result = redeem_points(seeded_db, session, account.member_number, guest.last_name, account.points_balance + 1000)

    assert "error" in result
    assert session.pending_action is None


def test_check_in_booking_not_confirmed_error(seeded_db):
    session = AgentSession()
    booking = _asha_booking(seeded_db)
    guest = _asha(seeded_db)
    booking_service.cancel_booking(seeded_db, booking.reference, guest.last_name)

    result = check_in(seeded_db, session, booking.reference, guest.last_name, "6 PM")

    assert "error" in result
    assert session.pending_action is None


# ---------------------------------------------------------------------------
# identity: find_booking / loyalty_status set session.guest_id
# ---------------------------------------------------------------------------


def test_find_booking_sets_session_guest_id(seeded_db):
    session = AgentSession()
    booking = _asha_booking(seeded_db)
    guest = _asha(seeded_db)

    result = find_booking(seeded_db, session, booking.reference, guest.last_name)

    assert "error" not in result
    assert session.guest_id == guest.id


def test_loyalty_status_sets_session_guest_id(seeded_db):
    session = AgentSession()
    account = _asha_loyalty(seeded_db)
    guest = _asha(seeded_db)

    result = loyalty_status(seeded_db, session, account.member_number, guest.last_name)

    assert "error" not in result
    assert session.guest_id == guest.id


# ---------------------------------------------------------------------------
# guest identity resolution for create_booking / enroll_loyalty / save_preferences
# ---------------------------------------------------------------------------


def test_create_booking_new_guest_creates_guest_and_sets_session_id(seeded_db):
    session = AgentSession()
    ci, co = (TODAY + timedelta(days=40)).isoformat(), (TODAY + timedelta(days=42)).isoformat()
    args = dict(room_type_code="standard", check_in=ci, check_out=co, num_guests=1, first_name="Fresh", last_name="Face")

    create_booking(seeded_db, session, **args)
    create_booking(seeded_db, session, **args)

    guest = seeded_db.scalar(select(Guest).where(Guest.first_name == "Fresh", Guest.last_name == "Face"))
    assert guest is not None
    assert session.guest_id == guest.id


def test_second_mutating_call_reuses_session_guest_id_no_duplicate(seeded_db):
    session = AgentSession()
    guest = _asha(seeded_db)
    session.guest_id = guest.id
    before_count = seeded_db.query(Guest).count()

    result = save_preferences(seeded_db, session, "vegetarian food")
    save_preferences(seeded_db, session, "vegetarian food, quiet room")

    assert seeded_db.query(Guest).count() == before_count
    assert result["guest_id"] == guest.id
    assert session.guest_id == guest.id


def test_create_booking_without_identity_returns_need_name_error(seeded_db):
    # propose doesn't need identity (just price/availability) - only confirm/execute does.
    session = AgentSession()
    ci, co = (TODAY + timedelta(days=1)).isoformat(), (TODAY + timedelta(days=2)).isoformat()
    args = dict(room_type_code="standard", check_in=ci, check_out=co, num_guests=1)

    proposed = create_booking(seeded_db, session, **args)
    assert "summary" in proposed
    assert session.pending_action is not None

    result = create_booking(seeded_db, session, **args)

    assert result == {"error": "I need your name to do that."}
    assert session.pending_action is None


# ---------------------------------------------------------------------------
# check_availability is read-only
# ---------------------------------------------------------------------------


def test_check_availability_no_filter(seeded_db):
    session = AgentSession()
    ci, co = (TODAY + timedelta(days=1)).isoformat(), (TODAY + timedelta(days=3)).isoformat()

    result = check_availability(seeded_db, session, ci, co)

    assert len(result["options"]) == 5


def test_check_availability_with_room_type_filter(seeded_db):
    session = AgentSession()
    ci, co = (TODAY + timedelta(days=1)).isoformat(), (TODAY + timedelta(days=3)).isoformat()

    result = check_availability(seeded_db, session, ci, co, room_type_code="standard")

    assert len(result["options"]) == 1
    assert result["options"][0]["room_type_code"] == "standard"
    before_row = _inventory_row(seeded_db, _room_type(seeded_db, "standard").id, TODAY + timedelta(days=1))
    assert before_row.rooms_booked == 0


# ---------------------------------------------------------------------------
# known edge case: modify_booking preview can under-report availability
# because it doesn't release the booking's own currently-held inventory
# before checking the new date range. The real service call always corrects
# for this (release-then-rebook), so this only affects the *preview* summary
# shown before confirmation.
# ---------------------------------------------------------------------------


def test_modify_booking_preview_wrongly_reports_no_availability_when_extending_a_full_room_type(seeded_db):
    session = AgentSession()
    ci, co = TODAY + timedelta(days=30), TODAY + timedelta(days=32)  # 2 nights, presidential_suite has 2 rooms
    guest_a = _make_guest(seeded_db, "A", "One")
    guest_b = _make_guest(seeded_db, "B", "Two")
    booking_a = booking_service.create_booking(seeded_db, guest_a.id, "presidential_suite", ci, co, 1)
    booking_service.create_booking(seeded_db, guest_b.id, "presidential_suite", ci, co, 1)

    new_check_out = (co + timedelta(days=1)).isoformat()  # extend booking_a by one night, same room type

    # Agent preview incorrectly says "no availability" ...
    preview = modify_booking(seeded_db, session, booking_a.reference, "One", check_out=new_check_out)
    assert "error" in preview, (
        "if this now passes, the preview bug has been fixed (or inventory setup changed) - "
        "update this test's expectation"
    )

    # ... even though the real service call (release-then-rebook) actually succeeds.
    real = booking_service.modify_booking(
        seeded_db, booking_a.reference, "One", check_out=date.fromisoformat(new_check_out)
    )
    assert real.check_out_date == date.fromisoformat(new_check_out)
