import pytest
from sqlalchemy import select

from app.models import Guest, LoyaltyAccount, LoyaltyTier
from app.services import loyalty as loyalty_service
from app.services.codes import ALPHABET


def _guest(db, last_name):
    return db.scalar(select(Guest).where(Guest.last_name == last_name))


def test_enroll_creates_silver_zero_point_account_with_unique_member_number(seeded_db):
    guest = _guest(seeded_db, "Verma")  # Rohan has no loyalty account yet

    account = loyalty_service.enroll(seeded_db, guest.id)

    assert account.tier == LoyaltyTier.SILVER
    assert account.points_balance == 0
    assert len(account.member_number) == 6
    assert set(account.member_number) <= set(ALPHABET)


def test_enroll_raises_on_double_enroll(seeded_db):
    guest = _guest(seeded_db, "Rao")  # Asha already has an account

    with pytest.raises(ValueError):
        loyalty_service.enroll(seeded_db, guest.id)


def test_get_status_works_and_fails_closed_on_wrong_last_name(seeded_db):
    account = seeded_db.scalar(select(LoyaltyAccount).join(Guest).where(Guest.last_name == "Mehta"))

    found = loyalty_service.get_status(seeded_db, account.member_number, "Mehta")
    assert found is not None
    assert found.id == account.id

    assert loyalty_service.get_status(seeded_db, account.member_number, "Wrong") is None
    # case-insensitive match
    assert loyalty_service.get_status(seeded_db, account.member_number.lower(), "mehta") is not None


def test_redeem_points_decrements_balance(seeded_db):
    account = seeded_db.scalar(select(LoyaltyAccount).join(Guest).where(Guest.last_name == "Mehta"))
    starting_balance = account.points_balance

    txn = loyalty_service.redeem_points(seeded_db, account.member_number, "Mehta", 200)

    assert txn.points_delta == -200
    seeded_db.refresh(account)
    assert account.points_balance == starting_balance - 200


def test_redeem_points_raises_when_exceeding_balance(seeded_db):
    account = seeded_db.scalar(select(LoyaltyAccount).join(Guest).where(Guest.last_name == "Mehta"))

    with pytest.raises(ValueError):
        loyalty_service.redeem_points(seeded_db, account.member_number, "Mehta", account.points_balance + 1)
