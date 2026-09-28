"""Real end-to-end proof of Phase 4: two multi-turn conversations driven
through the real OpenRouter endpoint (English and Hindi), each
with a read-only lookup followed by a full propose -> confirm cycle for a
mutating tool, confirmed via natural conversation (not repeated identical
tool args). Run with:

    cd backend && uv run python -m scripts.agent_transcript
"""

import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv(REPO_ROOT / ".env")

_DB_PATH = Path(tempfile.gettempdir()) / "hotel_assistant_agent_transcript.db"
if _DB_PATH.exists():
    _DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"

from sqlalchemy import select  # noqa: E402

from app.agent.loop import build_client, run_turn  # noqa: E402
from app.agent.session import AgentSession  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Booking, BookingStatus, Checkin, CheckinStatus, Guest  # noqa: E402
from app.seed import seed  # noqa: E402


def check(label: str, condition: bool) -> None:
    print(f"    {'PASS' if condition else 'FAIL'}: {label}")
    if not condition:
        sys.exit(f"Check failed: {label}")


def run_conversation(client, db, session, turns: list[str], label: str) -> None:
    print(f"\n=== {label} ===")
    history: list[dict] = []
    for user_message in turns:
        print(f"Guest:     {user_message}")
        reply = run_turn(client, db, session, history, user_message)
        print(f"Assistant: {reply}")


def main() -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        sys.exit("OPENROUTER_API_KEY not set (check .env at the repo root).")

    Base.metadata.create_all(bind=engine)
    seed()
    db = SessionLocal()
    client = build_client()

    asha = db.scalar(select(Guest).where(Guest.last_name == "Rao"))
    asha_booking = db.scalar(select(Booking).where(Booking.guest_id == asha.id))
    rohan = db.scalar(select(Guest).where(Guest.last_name == "Verma"))
    rohan_booking = db.scalar(select(Booking).where(Booking.guest_id == rohan.id))

    print(f"Asha Rao's booking reference: {asha_booking.reference}")
    print(f"Rohan Verma's booking reference: {rohan_booking.reference}")

    # --- English: read-only lookup (find_booking), then propose -> confirm check-in ---
    session_en = AgentSession()
    run_conversation(
        client,
        db,
        session_en,
        [
            f"Hi, my booking reference is {asha_booking.reference} and my last name is Rao, can you check it?",
            "I'd like to check in now, my arrival time is 6 PM.",
            "Yes, please go ahead.",
        ],
        "English transcript (Asha Rao: find_booking, then check_in propose->confirm)",
    )
    checkin = db.scalar(select(Checkin).where(Checkin.booking_id == asha_booking.id))
    print()
    check(
        "English: check-in was actually completed in the DB (not just described in text)",
        checkin is not None and checkin.status == CheckinStatus.COMPLETED,
    )

    # --- Hindi: read-only lookup (find_booking), then propose -> confirm cancel ---
    session_hi = AgentSession()
    run_conversation(
        client,
        db,
        session_hi,
        [
            f"नमस्ते, मेरा बुकिंग रेफरेंस {rohan_booking.reference} है और मेरा उपनाम वर्मा है, "
            "क्या आप इसे जांच सकते हैं?",
            "मैं इस बुकिंग को रद्द करना चाहता हूँ।",
            "हाँ, कृपया आगे बढ़ें।",
        ],
        "Hindi transcript (Rohan Verma: find_booking, then cancel_booking propose->confirm)",
    )
    db.refresh(rohan_booking)
    print()
    check(
        "Hindi: booking was actually cancelled in the DB (not just described in text)",
        rohan_booking.status == BookingStatus.CANCELLED,
    )

    db.close()
    engine.dispose()
    _DB_PATH.unlink(missing_ok=True)
    print("\nBoth transcripts completed and confirmed actions changed the DB.")
    sys.exit(0)


if __name__ == "__main__":
    main()
