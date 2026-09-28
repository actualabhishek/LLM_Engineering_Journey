from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, Checkin, Conversation, Guest, Message, RoomType


def list_bookings(db: Session) -> list[dict]:
    rows = db.execute(
        select(Booking, Guest, RoomType)
        .join(Guest, Booking.guest_id == Guest.id)
        .join(RoomType, Booking.room_type_id == RoomType.id)
        .order_by(Booking.created_at.desc())
    ).all()
    return [
        {
            "reference": booking.reference,
            "guest_name": f"{guest.first_name} {guest.last_name}",
            "room_type_name": room_type.name,
            "check_in_date": booking.check_in_date.isoformat(),
            "check_out_date": booking.check_out_date.isoformat(),
            "num_guests": booking.num_guests,
            "status": booking.status,
            "total_price_paise": booking.total_price_paise,
            "created_at": booking.created_at.isoformat(),
        }
        for booking, guest, room_type in rows
    ]


def list_checkins(db: Session) -> list[dict]:
    rows = db.execute(
        select(Checkin, Booking, Guest)
        .join(Booking, Checkin.booking_id == Booking.id)
        .join(Guest, Booking.guest_id == Guest.id)
        .order_by(Checkin.created_at.desc())
    ).all()
    return [
        {
            "booking_reference": booking.reference,
            "guest_name": f"{guest.first_name} {guest.last_name}",
            "arrival_time": checkin.arrival_time,
            "status": checkin.status,
            "special_requests": checkin.special_requests,
            "created_at": checkin.created_at.isoformat(),
        }
        for checkin, booking, guest in rows
    ]


def list_conversations(db: Session) -> list[dict]:
    message_count = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Conversation, Guest, message_count)
        .outerjoin(Guest, Conversation.guest_id == Guest.id)
        .order_by(Conversation.started_at.desc())
    ).all()
    return [
        {
            "id": conversation.id,
            "guest_name": f"{guest.first_name} {guest.last_name}" if guest else None,
            "started_at": conversation.started_at.isoformat(),
            "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
            "language": conversation.language,
            "message_count": count,
        }
        for conversation, guest, count in rows
    ]


def get_conversation_messages(db: Session, conversation_id: int) -> list[dict] | None:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        return None
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    ).all()
    return [
        {"role": message.role, "content": message.content, "created_at": message.created_at.isoformat()}
        for message in messages
    ]
