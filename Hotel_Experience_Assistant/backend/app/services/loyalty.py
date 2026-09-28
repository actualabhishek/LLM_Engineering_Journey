from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Guest, LoyaltyAccount, LoyaltyTransaction
from app.services.codes import generate_unique_code


def get_status(db: Session, member_number: str, last_name: str) -> LoyaltyAccount | None:
    return db.scalar(
        select(LoyaltyAccount).join(Guest).where(
            func.upper(LoyaltyAccount.member_number) == member_number.upper(),
            func.lower(Guest.last_name) == last_name.lower(),
        )
    )


def enroll(db: Session, guest_id: int) -> LoyaltyAccount:
    existing = db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.guest_id == guest_id))
    if existing is not None:
        raise ValueError("guest already has a loyalty account")

    member_number = generate_unique_code(db, LoyaltyAccount, "member_number")
    account = LoyaltyAccount(member_number=member_number, guest_id=guest_id)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def redeem_points(db: Session, member_number: str, last_name: str, points: int) -> LoyaltyTransaction:
    account = get_status(db, member_number, last_name)
    if account is None:
        raise ValueError("loyalty account not found")
    if account.points_balance < points:
        raise ValueError("insufficient points balance")

    account.points_balance -= points
    transaction = LoyaltyTransaction(loyalty_account_id=account.id, points_delta=-points, reason="redeem")
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction
