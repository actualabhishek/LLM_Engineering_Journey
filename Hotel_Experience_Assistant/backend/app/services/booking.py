from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Guest, Inventory, LoyaltyAccount, LoyaltyTransaction, RoomType
from app.services.codes import generate_unique_code


def _dates(check_in: date, check_out: date) -> list[date]:
    return [check_in + timedelta(days=i) for i in range((check_out - check_in).days)]


def _get_room_type(db: Session, code: str) -> RoomType:
    room_type = db.scalar(select(RoomType).where(RoomType.code == code))
    if room_type is None:
        raise ValueError(f"unknown room type: {code}")
    return room_type


def _is_available(db: Session, room_type: RoomType, check_in: date, check_out: date) -> bool:
    dates = _dates(check_in, check_out)
    rows = db.scalars(
        select(Inventory).where(Inventory.room_type_id == room_type.id, Inventory.date.in_(dates))
    ).all()
    by_date = {row.date: row for row in rows}
    return all(
        (row := by_date.get(d)) is not None and row.rooms_booked < room_type.total_rooms for d in dates
    )


def _book_dates(db: Session, room_type: RoomType, check_in: date, check_out: date) -> None:
    rows = db.scalars(
        select(Inventory).where(
            Inventory.room_type_id == room_type.id, Inventory.date.in_(_dates(check_in, check_out))
        )
    ).all()
    for row in rows:
        row.rooms_booked += 1


def _release_dates(db: Session, room_type_id: int, check_in: date, check_out: date) -> None:
    rows = db.scalars(
        select(Inventory).where(
            Inventory.room_type_id == room_type_id, Inventory.date.in_(_dates(check_in, check_out))
        )
    ).all()
    for row in rows:
        row.rooms_booked -= 1


def _sync_points(db: Session, guest_id: int, booking_id: int, target_total_paise: int, reason: str) -> None:
    account = db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.guest_id == guest_id))
    if account is None:
        return
    existing = (
        db.scalar(select(func.sum(LoyaltyTransaction.points_delta)).where(LoyaltyTransaction.booking_id == booking_id))
        or 0
    )
    target_points = target_total_paise // 1000
    delta = target_points - existing
    if delta == 0:
        return
    account.points_balance += delta
    db.add(LoyaltyTransaction(loyalty_account_id=account.id, points_delta=delta, reason=reason, booking_id=booking_id))


def check_availability(
    db: Session, check_in: date, check_out: date, room_type_code: str | None = None
) -> list[dict]:
    nights = (check_out - check_in).days
    query = select(RoomType)
    if room_type_code is not None:
        query = query.where(RoomType.code == room_type_code)
    room_types = db.scalars(query).all()
    results = []
    for room_type in room_types:
        if _is_available(db, room_type, check_in, check_out):
            results.append(
                {
                    "room_type_code": room_type.code,
                    "name": room_type.name,
                    "nightly_price_paise": room_type.base_price_paise,
                    "nights": nights,
                    "total_price_paise": room_type.base_price_paise * nights,
                }
            )
    return results


def create_booking(
    db: Session,
    guest_id: int,
    room_type_code: str,
    check_in: date,
    check_out: date,
    num_guests: int,
    special_requests: str | None = None,
) -> Booking:
    room_type = _get_room_type(db, room_type_code)
    if not _is_available(db, room_type, check_in, check_out):
        raise ValueError(f"no availability for {room_type_code} from {check_in} to {check_out}")
    nights = (check_out - check_in).days
    total_price_paise = room_type.base_price_paise * nights
    _book_dates(db, room_type, check_in, check_out)
    reference = generate_unique_code(db, Booking, "reference")
    booking = Booking(
        reference=reference,
        guest_id=guest_id,
        room_type_id=room_type.id,
        check_in_date=check_in,
        check_out_date=check_out,
        num_guests=num_guests,
        total_price_paise=total_price_paise,
        special_requests=special_requests,
    )
    db.add(booking)
    db.flush()
    _sync_points(db, guest_id, booking.id, total_price_paise, "booking_earn")
    db.commit()
    db.refresh(booking)
    return booking


def find_booking(db: Session, reference: str, last_name: str) -> Booking | None:
    return db.scalar(
        select(Booking).join(Guest).where(
            func.upper(Booking.reference) == reference.upper(),
            func.lower(Guest.last_name) == last_name.lower(),
        )
    )


def modify_booking(
    db: Session,
    reference: str,
    last_name: str,
    room_type_code: str | None = None,
    check_in: date | None = None,
    check_out: date | None = None,
    num_guests: int | None = None,
    special_requests: str | None = None,
) -> Booking:
    booking = find_booking(db, reference, last_name)
    if booking is None:
        raise ValueError("booking not found")
    if booking.status != BookingStatus.CONFIRMED:
        raise ValueError("booking is not confirmed")

    old_room_type = db.get(RoomType, booking.room_type_id)
    old_check_in, old_check_out = booking.check_in_date, booking.check_out_date
    new_room_type_code = room_type_code or old_room_type.code
    new_check_in = check_in or old_check_in
    new_check_out = check_out or old_check_out
    dates_changed = (
        new_room_type_code != old_room_type.code
        or new_check_in != old_check_in
        or new_check_out != old_check_out
    )

    if dates_changed:
        new_room_type = _get_room_type(db, new_room_type_code)
        _release_dates(db, old_room_type.id, old_check_in, old_check_out)
        if not _is_available(db, new_room_type, new_check_in, new_check_out):
            _book_dates(db, old_room_type, old_check_in, old_check_out)
            raise ValueError("no availability for the requested change")
        _book_dates(db, new_room_type, new_check_in, new_check_out)
        nights = (new_check_out - new_check_in).days
        booking.room_type_id = new_room_type.id
        booking.check_in_date = new_check_in
        booking.check_out_date = new_check_out
        booking.total_price_paise = new_room_type.base_price_paise * nights
        _sync_points(db, booking.guest_id, booking.id, booking.total_price_paise, "booking_earn")

    if num_guests is not None:
        booking.num_guests = num_guests
    if special_requests is not None:
        booking.special_requests = special_requests

    db.commit()
    db.refresh(booking)
    return booking


def cancel_booking(db: Session, reference: str, last_name: str) -> Booking:
    booking = find_booking(db, reference, last_name)
    if booking is None:
        raise ValueError("booking not found")
    if booking.status != BookingStatus.CONFIRMED:
        raise ValueError("booking is not confirmed")

    _release_dates(db, booking.room_type_id, booking.check_in_date, booking.check_out_date)
    booking.status = BookingStatus.CANCELLED
    _sync_points(db, booking.guest_id, booking.id, 0, "booking_cancelled")
    db.commit()
    db.refresh(booking)
    return booking
