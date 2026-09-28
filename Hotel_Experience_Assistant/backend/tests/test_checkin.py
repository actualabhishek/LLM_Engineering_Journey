from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Checkin, CheckinStatus, Guest
from app.services import booking as booking_service
from app.services import checkin as checkin_service

TODAY = date.today()


def _make_guest(db, first_name="Test", last_name="Guest"):
    guest = Guest(first_name=first_name, last_name=last_name)
    db.add(guest)
    db.commit()
    db.refresh(guest)
    return guest


def test_check_in_succeeds_on_confirmed_booking(seeded_db):
    guest = _make_guest(seeded_db)
    booking = booking_service.create_booking(
        seeded_db, guest.id, "standard", TODAY + timedelta(days=20), TODAY + timedelta(days=22), 1
    )

    checkin = checkin_service.check_in(seeded_db, booking.reference, guest.last_name, "15:00", "late arrival")

    assert checkin.status == CheckinStatus.COMPLETED
    assert checkin.arrival_time == "15:00"
    stored = seeded_db.scalar(select(Checkin).where(Checkin.booking_id == booking.id))
    assert stored is not None
    assert stored.status == CheckinStatus.COMPLETED


def test_check_in_raises_on_cancelled_booking(seeded_db):
    guest = _make_guest(seeded_db)
    booking = booking_service.create_booking(
        seeded_db, guest.id, "standard", TODAY + timedelta(days=20), TODAY + timedelta(days=22), 1
    )
    booking_service.cancel_booking(seeded_db, booking.reference, guest.last_name)

    with pytest.raises(ValueError):
        checkin_service.check_in(seeded_db, booking.reference, guest.last_name, "15:00")


def test_check_in_raises_on_wrong_identity(seeded_db):
    guest = _make_guest(seeded_db)
    booking = booking_service.create_booking(
        seeded_db, guest.id, "standard", TODAY + timedelta(days=20), TODAY + timedelta(days=22), 1
    )

    with pytest.raises(ValueError):
        checkin_service.check_in(seeded_db, booking.reference, "WrongName", "15:00")
