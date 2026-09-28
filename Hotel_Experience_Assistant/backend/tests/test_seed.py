from datetime import date

from sqlalchemy import select

from app.models import Booking, BookingStatus, Guest, Inventory, LoyaltyAccount, LoyaltyTier, RoomType
from app.seed import seed


def _guest(db, last_name):
    return db.scalar(select(Guest).where(Guest.last_name == last_name))


def test_seed_is_idempotent(seeded_db):
    room_type_count = seeded_db.query(RoomType).count()
    guest_count = seeded_db.query(Guest).count()
    inventory_count = seeded_db.query(Inventory).count()
    booking_count = seeded_db.query(Booking).count()

    seed()

    assert seeded_db.query(RoomType).count() == room_type_count
    assert seeded_db.query(Guest).count() == guest_count
    assert seeded_db.query(Inventory).count() == inventory_count
    assert seeded_db.query(Booking).count() == booking_count


def test_seed_creates_room_types_and_inventory(seeded_db):
    assert seeded_db.query(RoomType).count() == 5
    assert seeded_db.query(Inventory).count() == 60 * 5


def test_seed_creates_four_demo_guests(seeded_db):
    names = {(g.first_name, g.last_name) for g in seeded_db.query(Guest).all()}
    assert names == {
        ("Asha", "Rao"),
        ("Vikram", "Mehta"),
        ("Neha", "Kapoor"),
        ("Rohan", "Verma"),
    }


def test_asha_rao_silver_with_upcoming_confirmed_booking(seeded_db):
    guest = _guest(seeded_db, "Rao")
    account = seeded_db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.guest_id == guest.id))
    assert account.tier == LoyaltyTier.SILVER
    assert account.points_balance == 1050  # 3 nights x standard room (350000 paise/night) // 1000

    booking = seeded_db.scalar(select(Booking).where(Booking.guest_id == guest.id))
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.check_in_date > date.today()


def test_vikram_mehta_gold_with_past_booking(seeded_db):
    guest = _guest(seeded_db, "Mehta")
    account = seeded_db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.guest_id == guest.id))
    assert account.tier == LoyaltyTier.GOLD
    assert account.points_balance == 1200

    booking = seeded_db.scalar(select(Booking).where(Booking.guest_id == guest.id))
    assert booking.check_out_date < date.today()


def test_neha_kapoor_platinum_with_no_booking(seeded_db):
    guest = _guest(seeded_db, "Kapoor")
    account = seeded_db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.guest_id == guest.id))
    assert account.tier == LoyaltyTier.PLATINUM
    assert account.points_balance == 5000

    booking = seeded_db.scalar(select(Booking).where(Booking.guest_id == guest.id))
    assert booking is None


def test_rohan_verma_no_loyalty_account_with_confirmed_booking(seeded_db):
    guest = _guest(seeded_db, "Verma")
    account = seeded_db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.guest_id == guest.id))
    assert account is None

    booking = seeded_db.scalar(select(Booking).where(Booking.guest_id == guest.id))
    assert booking is not None
    assert booking.status == BookingStatus.CONFIRMED
