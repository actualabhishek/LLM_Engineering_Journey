from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Booking, BookingStatus, Guest, Inventory, LoyaltyAccount, LoyaltyTransaction, RoomType
from app.services import booking as booking_service
from app.services import loyalty as loyalty_service
from app.services.codes import ALPHABET

TODAY = date.today()


def _make_guest(db, first_name="Test", last_name="Guest"):
    guest = Guest(first_name=first_name, last_name=last_name)
    db.add(guest)
    db.commit()
    db.refresh(guest)
    return guest


def _room_type(db, code):
    return db.scalar(select(RoomType).where(RoomType.code == code))


def _inventory_row(db, room_type_id, day):
    return db.scalar(
        select(Inventory).where(Inventory.room_type_id == room_type_id, Inventory.date == day)
    )


def _member_number(db, guest_id):
    account = db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.guest_id == guest_id))
    return account.member_number


def test_check_availability_returns_room_types_and_prices(seeded_db):
    check_in, check_out = TODAY + timedelta(days=1), TODAY + timedelta(days=3)
    results = booking_service.check_availability(seeded_db, check_in, check_out)

    assert len(results) == 5
    standard = next(r for r in results if r["room_type_code"] == "standard")
    assert standard["nightly_price_paise"] == 350000
    assert standard["nights"] == 2
    assert standard["total_price_paise"] == 700000


def test_check_availability_filtered_by_room_type_code(seeded_db):
    check_in, check_out = TODAY + timedelta(days=1), TODAY + timedelta(days=2)
    results = booking_service.check_availability(seeded_db, check_in, check_out, room_type_code="deluxe")

    assert len(results) == 1
    assert results[0]["room_type_code"] == "deluxe"


def test_create_booking_decrements_availability(seeded_db):
    room_type = _room_type(seeded_db, "standard")
    check_in, check_out = TODAY + timedelta(days=20), TODAY + timedelta(days=22)
    guest = _make_guest(seeded_db)

    booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)

    for day in (check_in, check_in + timedelta(days=1)):
        row = _inventory_row(seeded_db, room_type.id, day)
        assert row.rooms_booked == 1


def test_create_booking_reference_uses_safe_alphabet(seeded_db):
    guest = _make_guest(seeded_db)
    check_in, check_out = TODAY + timedelta(days=20), TODAY + timedelta(days=22)

    booking = booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)

    assert len(booking.reference) == 6
    assert set(booking.reference) <= set(ALPHABET)
    assert not set(booking.reference) & set("01OIL")


def test_create_booking_awards_points_when_guest_has_loyalty_account(seeded_db):
    guest = _make_guest(seeded_db)
    loyalty_service.enroll(seeded_db, guest.id)
    check_in, check_out = TODAY + timedelta(days=20), TODAY + timedelta(days=23)

    booking = booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)

    expected_points = booking.total_price_paise // 1000
    account = loyalty_service.get_status(seeded_db, _member_number(seeded_db, guest.id), guest.last_name)
    assert account.points_balance == expected_points
    txn = seeded_db.scalar(select(LoyaltyTransaction).where(LoyaltyTransaction.booking_id == booking.id))
    assert txn.points_delta == expected_points
    assert txn.reason == "booking_earn"


def test_create_booking_awards_no_points_without_loyalty_account(seeded_db):
    guest = _make_guest(seeded_db)
    check_in, check_out = TODAY + timedelta(days=20), TODAY + timedelta(days=22)

    booking = booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)

    count = seeded_db.scalar(
        select(func.count()).select_from(LoyaltyTransaction).where(LoyaltyTransaction.booking_id == booking.id)
    )
    assert count == 0


def test_find_booking_succeeds_and_fails_closed_on_wrong_last_name(seeded_db):
    guest = _make_guest(seeded_db, "Priya", "Nair")
    check_in, check_out = TODAY + timedelta(days=20), TODAY + timedelta(days=22)
    booking = booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)

    found = booking_service.find_booking(seeded_db, booking.reference, "Nair")
    assert found is not None
    assert found.id == booking.id

    assert booking_service.find_booking(seeded_db, booking.reference, "Wrong") is None
    # case-insensitive match
    assert booking_service.find_booking(seeded_db, booking.reference.lower(), "nair") is not None


def test_modify_booking_room_type_change_updates_price_and_inventory(seeded_db):
    guest = _make_guest(seeded_db)
    loyalty_service.enroll(seeded_db, guest.id)
    check_in, check_out = TODAY + timedelta(days=20), TODAY + timedelta(days=22)
    booking = booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)

    standard = _room_type(seeded_db, "standard")
    deluxe = _room_type(seeded_db, "deluxe")

    updated = booking_service.modify_booking(seeded_db, booking.reference, guest.last_name, room_type_code="deluxe")

    assert updated.room_type_id == deluxe.id
    assert updated.total_price_paise == deluxe.base_price_paise * 2
    assert _inventory_row(seeded_db, standard.id, check_in).rooms_booked == 0
    assert _inventory_row(seeded_db, deluxe.id, check_in).rooms_booked == 1

    expected_points = updated.total_price_paise // 1000
    net_points = seeded_db.scalar(
        select(func.sum(LoyaltyTransaction.points_delta)).where(LoyaltyTransaction.booking_id == booking.id)
    )
    assert net_points == expected_points


def test_modify_booking_date_change_updates_price_and_inventory(seeded_db):
    guest = _make_guest(seeded_db)
    check_in, check_out = TODAY + timedelta(days=20), TODAY + timedelta(days=22)
    booking = booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)

    room_type = _room_type(seeded_db, "standard")
    new_check_in, new_check_out = TODAY + timedelta(days=25), TODAY + timedelta(days=29)

    updated = booking_service.modify_booking(
        seeded_db, booking.reference, guest.last_name, check_in=new_check_in, check_out=new_check_out
    )

    assert updated.check_in_date == new_check_in
    assert updated.check_out_date == new_check_out
    assert updated.total_price_paise == room_type.base_price_paise * 4
    assert _inventory_row(seeded_db, room_type.id, check_in).rooms_booked == 0
    assert _inventory_row(seeded_db, room_type.id, new_check_in).rooms_booked == 1


def test_cancel_booking_releases_inventory_and_zeroes_net_points(seeded_db):
    guest = _make_guest(seeded_db)
    loyalty_service.enroll(seeded_db, guest.id)
    check_in, check_out = TODAY + timedelta(days=20), TODAY + timedelta(days=22)
    booking = booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)
    room_type = _room_type(seeded_db, "standard")

    cancelled = booking_service.cancel_booking(seeded_db, booking.reference, guest.last_name)

    assert cancelled.status == BookingStatus.CANCELLED
    assert _inventory_row(seeded_db, room_type.id, check_in).rooms_booked == 0
    net_points = seeded_db.scalar(
        select(func.sum(LoyaltyTransaction.points_delta)).where(LoyaltyTransaction.booking_id == booking.id)
    )
    assert net_points == 0


def test_create_booking_beyond_inventory_horizon_raises(seeded_db):
    guest = _make_guest(seeded_db)
    check_in, check_out = TODAY + timedelta(days=60), TODAY + timedelta(days=62)

    with pytest.raises(ValueError):
        booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)


def test_cancel_booking_twice_raises_and_does_not_double_release_inventory(seeded_db):
    guest = _make_guest(seeded_db)
    check_in, check_out = TODAY + timedelta(days=20), TODAY + timedelta(days=22)
    booking = booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)
    room_type = _room_type(seeded_db, "standard")

    booking_service.cancel_booking(seeded_db, booking.reference, guest.last_name)

    with pytest.raises(ValueError):
        booking_service.cancel_booking(seeded_db, booking.reference, guest.last_name)

    assert _inventory_row(seeded_db, room_type.id, check_in).rooms_booked == 0


def test_modify_cancelled_booking_raises(seeded_db):
    guest = _make_guest(seeded_db)
    check_in, check_out = TODAY + timedelta(days=20), TODAY + timedelta(days=22)
    booking = booking_service.create_booking(seeded_db, guest.id, "standard", check_in, check_out, 1)
    booking_service.cancel_booking(seeded_db, booking.reference, guest.last_name)

    with pytest.raises(ValueError):
        booking_service.modify_booking(seeded_db, booking.reference, guest.last_name, room_type_code="deluxe")


def test_double_booking_all_remaining_rooms_then_one_more_raises(seeded_db):
    room_type = _room_type(seeded_db, "presidential_suite")
    assert room_type.total_rooms == 2
    check_in, check_out = TODAY + timedelta(days=30), TODAY + timedelta(days=31)

    guest_a = _make_guest(seeded_db, "A", "One")
    guest_b = _make_guest(seeded_db, "B", "Two")
    guest_c = _make_guest(seeded_db, "C", "Three")

    booking_service.create_booking(seeded_db, guest_a.id, "presidential_suite", check_in, check_out, 1)
    booking_service.create_booking(seeded_db, guest_b.id, "presidential_suite", check_in, check_out, 1)

    with pytest.raises(ValueError):
        booking_service.create_booking(seeded_db, guest_c.id, "presidential_suite", check_in, check_out, 1)
