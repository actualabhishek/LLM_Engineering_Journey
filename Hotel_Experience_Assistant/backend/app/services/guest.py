from sqlalchemy.orm import Session

from app.models import Guest


def create(db: Session, first_name: str, last_name: str) -> Guest:
    guest = Guest(first_name=first_name, last_name=last_name)
    db.add(guest)
    db.commit()
    db.refresh(guest)
    return guest


def save_preferences(db: Session, guest_id: int, preferences: str) -> Guest:
    guest = db.get(Guest, guest_id)
    guest.preferences = preferences
    db.commit()
    db.refresh(guest)
    return guest
