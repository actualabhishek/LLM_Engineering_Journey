from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BookingStatus, Checkin, CheckinStatus
from app.services.booking import find_booking


def check_in(
    db: Session,
    reference: str,
    last_name: str,
    arrival_time: str,
    special_requests: str | None = None,
) -> Checkin:
    booking = find_booking(db, reference, last_name)
    if booking is None:
        raise ValueError("booking not found")
    if booking.status != BookingStatus.CONFIRMED:
        raise ValueError("booking is not confirmed")

    checkin = db.scalar(select(Checkin).where(Checkin.booking_id == booking.id))
    if checkin is None:
        checkin = Checkin(booking_id=booking.id)
        db.add(checkin)

    checkin.arrival_time = arrival_time
    checkin.special_requests = special_requests
    checkin.status = CheckinStatus.COMPLETED
    db.commit()
    db.refresh(checkin)
    return checkin
