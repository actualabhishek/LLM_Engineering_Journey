import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
DIGITS = "23456789"


def generate_unique_code(db: Session, model, column_name: str, length: int = 6) -> str:
    column = getattr(model, column_name)
    for _ in range(10):
        code = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if all(c in DIGITS for c in code):
            continue  # an all-digit code would get mangled by Hindi number-to-words TTS normalization
        exists = db.scalar(select(column).where(column == code))
        if exists is None:
            return code
    raise RuntimeError(f"could not generate a unique code for {model.__name__}.{column_name}")
