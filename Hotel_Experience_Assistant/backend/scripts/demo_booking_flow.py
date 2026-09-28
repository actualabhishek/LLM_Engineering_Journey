"""Proof that booking + loyalty services work end to end: enroll a guest,
check availability, create a booking, modify it, then cancel it, printing
the confirmation summary at each step. Run with:

    cd backend && uv run python -m scripts.demo_booking_flow
"""

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

_DB_PATH = Path(tempfile.gettempdir()) / "hotel_assistant_demo.db"
if _DB_PATH.exists():
    _DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed  # noqa: E402
from app.services import booking as booking_service  # noqa: E402
from app.services import loyalty as loyalty_service  # noqa: E402
from app.models import Guest, LoyaltyTransaction  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

TODAY = date.today()


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"    {status}: {label}")
    if not condition:
        sys.exit(f"Check failed: {label}")


def main() -> None:
    Base.metadata.create_all(bind=engine)
    seed()
    db = SessionLocal()

    print("[1] Seeded database with room types, inventory and demo guests.")

    guest = Guest(first_name="Demo", last_name="Guest")
    db.add(guest)
    db.commit()
    db.refresh(guest)
    account = loyalty_service.enroll(db, guest.id)
    print(f"[2] Enrolled guest: member_number={account.member_number} tier={account.tier} points={account.points_balance}")
    check("new account is silver with 0 points", account.points_balance == 0)

    check_in, check_out = TODAY + timedelta(days=10), TODAY + timedelta(days=13)
    availability = booking_service.check_availability(db, check_in, check_out, room_type_code="deluxe")
    print(f"[3] Availability for deluxe {check_in} -> {check_out}: {availability}")
    check("deluxe is available", len(availability) == 1)

    booking = booking_service.create_booking(db, guest.id, "deluxe", check_in, check_out, 2)
    db.refresh(account)
    print(
        f"[4] Booked: reference={booking.reference} room=deluxe nights=3 "
        f"total_price_paise={booking.total_price_paise} points_balance={account.points_balance}"
    )
    expected_points = booking.total_price_paise // 1000
    check("points earned matches total_price_paise // 1000", account.points_balance == expected_points)

    new_check_in, new_check_out = TODAY + timedelta(days=15), TODAY + timedelta(days=17)
    modified = booking_service.modify_booking(
        db, booking.reference, guest.last_name, check_in=new_check_in, check_out=new_check_out
    )
    db.refresh(account)
    print(
        f"[5] Modified dates to {modified.check_in_date} -> {modified.check_out_date}: "
        f"total_price_paise={modified.total_price_paise} points_balance={account.points_balance}"
    )
    expected_points = modified.total_price_paise // 1000
    check("points re-synced after date change", account.points_balance == expected_points)

    cancelled = booking_service.cancel_booking(db, booking.reference, guest.last_name)
    db.refresh(account)
    print(f"[6] Cancelled {cancelled.reference}: status={cancelled.status} points_balance={account.points_balance}")
    check("cancelling zeroes points earned by this booking", account.points_balance == 0)

    net_points = db.scalar(
        select(func.sum(LoyaltyTransaction.points_delta)).where(LoyaltyTransaction.booking_id == booking.id)
    )
    print(f"[7] Net loyalty points from this booking after cancel: {net_points}")
    check("net points from the booking's transactions is 0", net_points == 0)

    db.close()
    engine.dispose()
    _DB_PATH.unlink(missing_ok=True)
    print("All checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
