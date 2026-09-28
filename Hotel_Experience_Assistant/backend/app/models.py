import enum
from datetime import date, datetime

from sqlalchemy import Date, Enum, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class BookingStatus(enum.StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class LoyaltyTier(enum.StrEnum):
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class CheckinStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


class RoomType(Base):
    __tablename__ = "room_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    description: Mapped[str]
    base_price_paise: Mapped[int]
    max_occupancy: Mapped[int]
    total_rooms: Mapped[int]


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (UniqueConstraint("room_type_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"))
    date: Mapped[date] = mapped_column(Date)
    rooms_booked: Mapped[int] = mapped_column(default=0)


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str]
    last_name: Mapped[str]
    preferences: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    loyalty_account: Mapped["LoyaltyAccount"] = relationship(back_populates="guest")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(unique=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"))
    room_type_id: Mapped[int] = mapped_column(ForeignKey("room_types.id"))
    check_in_date: Mapped[date] = mapped_column(Date)
    check_out_date: Mapped[date] = mapped_column(Date)
    num_guests: Mapped[int]
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, create_constraint=True), default=BookingStatus.CONFIRMED
    )
    total_price_paise: Mapped[int]
    special_requests: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LoyaltyAccount(Base):
    __tablename__ = "loyalty_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_number: Mapped[str] = mapped_column(unique=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), unique=True)
    tier: Mapped[LoyaltyTier] = mapped_column(
        Enum(LoyaltyTier, create_constraint=True), default=LoyaltyTier.SILVER
    )
    points_balance: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    guest: Mapped["Guest"] = relationship(back_populates="loyalty_account")


class LoyaltyTransaction(Base):
    __tablename__ = "loyalty_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    loyalty_account_id: Mapped[int] = mapped_column(ForeignKey("loyalty_accounts.id"))
    points_delta: Mapped[int]
    reason: Mapped[str]
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), unique=True)
    arrival_time: Mapped[str]
    status: Mapped[CheckinStatus] = mapped_column(
        Enum(CheckinStatus, create_constraint=True), default=CheckinStatus.PENDING
    )
    special_requests: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int | None] = mapped_column(ForeignKey("guests.id"))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ended_at: Mapped[datetime | None]
    language: Mapped[str | None]


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str]
    content: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
