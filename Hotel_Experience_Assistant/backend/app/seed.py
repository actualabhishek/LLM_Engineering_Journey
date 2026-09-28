from datetime import date, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Booking, Guest, Inventory, LoyaltyAccount, LoyaltyTier, RoomType
from app.services import booking as booking_service
from app.services import codes
from app.services import loyalty as loyalty_service

INVENTORY_DAYS = 60

ROOM_TYPES = [
    dict(
        code="standard",
        name="Standard Room",
        description="Cosy room with a queen bed, city view and free Wi-Fi.",
        base_price_paise=350000,
        max_occupancy=2,
        total_rooms=20,
    ),
    dict(
        code="deluxe",
        name="Deluxe Room",
        description="Spacious room with a king bed, lounge chair and garden view.",
        base_price_paise=550000,
        max_occupancy=2,
        total_rooms=15,
    ),
    dict(
        code="executive_suite",
        name="Executive Suite",
        description="Separate living area, work desk and lounge access.",
        base_price_paise=900000,
        max_occupancy=3,
        total_rooms=10,
    ),
    dict(
        code="family_suite",
        name="Family Suite",
        description="Two-room suite with a bunk nook, ideal for families.",
        base_price_paise=1100000,
        max_occupancy=5,
        total_rooms=8,
    ),
    dict(
        code="presidential_suite",
        name="Presidential Suite",
        description="Top-floor suite with a private terrace and butler service.",
        base_price_paise=2500000,
        max_occupancy=4,
        total_rooms=2,
    ),
]


def seed() -> None:
    db = SessionLocal()
    try:
        if db.query(RoomType).first() is not None:
            return

        room_types = [RoomType(**fields) for fields in ROOM_TYPES]
        db.add_all(room_types)
        db.flush()

        today = date.today()
        for room_type in room_types:
            for offset in range(INVENTORY_DAYS):
                db.add(Inventory(room_type_id=room_type.id, date=today + timedelta(days=offset), rooms_booked=0))
        db.commit()

        _seed_guests(db, today)
    finally:
        db.close()


def _seed_guests(db, today: date) -> None:
    asha = Guest(first_name="Asha", last_name="Rao")
    db.add(asha)
    db.commit()
    db.refresh(asha)
    loyalty_service.enroll(db, asha.id)
    booking_service.create_booking(
        db, asha.id, "standard", today + timedelta(days=10), today + timedelta(days=13), 2
    )

    vikram = Guest(first_name="Vikram", last_name="Mehta")
    db.add(vikram)
    db.commit()
    db.refresh(vikram)
    db.add(
        LoyaltyAccount(
            member_number=codes.generate_unique_code(db, LoyaltyAccount, "member_number"),
            guest_id=vikram.id,
            tier=LoyaltyTier.GOLD,
            points_balance=1200,
        )
    )
    deluxe = db.scalar(select(RoomType).where(RoomType.code == "deluxe"))
    past_check_in = today - timedelta(days=30)
    past_check_out = today - timedelta(days=27)
    db.add(
        Booking(
            reference=codes.generate_unique_code(db, Booking, "reference"),
            guest_id=vikram.id,
            room_type_id=deluxe.id,
            check_in_date=past_check_in,
            check_out_date=past_check_out,
            num_guests=2,
            total_price_paise=deluxe.base_price_paise * (past_check_out - past_check_in).days,
        )
    )
    db.commit()

    neha = Guest(first_name="Neha", last_name="Kapoor")
    db.add(neha)
    db.commit()
    db.refresh(neha)
    account = loyalty_service.enroll(db, neha.id)
    account.tier = LoyaltyTier.PLATINUM
    account.points_balance = 5000
    db.commit()

    rohan = Guest(first_name="Rohan", last_name="Verma")
    db.add(rohan)
    db.commit()
    db.refresh(rohan)
    booking_service.create_booking(
        db, rohan.id, "family_suite", today + timedelta(days=5), today + timedelta(days=7), 4
    )


if __name__ == "__main__":
    seed()
