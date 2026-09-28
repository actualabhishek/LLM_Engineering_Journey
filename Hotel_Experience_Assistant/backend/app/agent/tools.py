from datetime import date
from typing import Callable

from app.agent.session import AgentSession, PendingAction
from app.models import BookingStatus, RoomType
from app.services import booking as booking_service
from app.services import checkin as checkin_service
from app.services import guest as guest_service
from app.services import loyalty as loyalty_service

ROOM_TYPE_HINT = "Room type code: standard, deluxe, executive_suite, family_suite, or presidential_suite."

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check room availability and price for a date range. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "check_in": {"type": "string", "description": "Check-in date, YYYY-MM-DD."},
                    "check_out": {"type": "string", "description": "Check-out date, YYYY-MM-DD."},
                    "room_type_code": {"type": "string", "description": ROOM_TYPE_HINT},
                },
                "required": ["check_in", "check_out"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": (
                "Propose creating a booking, then create it after the guest confirms. "
                "Call once to get a summary and price, call again with the same arguments after the guest says yes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "room_type_code": {"type": "string", "description": ROOM_TYPE_HINT},
                    "check_in": {"type": "string", "description": "Check-in date, YYYY-MM-DD."},
                    "check_out": {"type": "string", "description": "Check-out date, YYYY-MM-DD."},
                    "num_guests": {"type": "integer"},
                    "special_requests": {"type": "string"},
                    "first_name": {
                        "type": "string",
                        "description": "Guest's first name. Only needed if this is a brand new guest.",
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Guest's last name. Only needed if this is a brand new guest.",
                    },
                },
                "required": ["room_type_code", "check_in", "check_out", "num_guests"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_booking",
            "description": "Look up an existing booking by reference and last name. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string"},
                    "last_name": {"type": "string"},
                },
                "required": ["reference", "last_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_booking",
            "description": (
                "Propose changes to an existing booking, then apply them after the guest confirms. "
                "Call once to get a summary and new price, call again with the same arguments after the guest says yes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string"},
                    "last_name": {"type": "string"},
                    "room_type_code": {"type": "string", "description": ROOM_TYPE_HINT},
                    "check_in": {"type": "string", "description": "New check-in date, YYYY-MM-DD."},
                    "check_out": {"type": "string", "description": "New check-out date, YYYY-MM-DD."},
                    "num_guests": {"type": "integer"},
                    "special_requests": {"type": "string"},
                },
                "required": ["reference", "last_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_booking",
            "description": (
                "Propose cancelling a booking, then cancel it after the guest confirms. "
                "Call once to get a summary, call again with the same arguments after the guest says yes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string"},
                    "last_name": {"type": "string"},
                },
                "required": ["reference", "last_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "loyalty_status",
            "description": "Look up a loyalty account by member number and last name. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_number": {"type": "string"},
                    "last_name": {"type": "string"},
                },
                "required": ["member_number", "last_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enroll_loyalty",
            "description": (
                "Propose enrolling the guest in the loyalty program, then enroll them after they confirm. "
                "Call once to get a summary, call again with the same arguments after the guest says yes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {
                        "type": "string",
                        "description": "Guest's first name. Only needed if this is a brand new guest.",
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Guest's last name. Only needed if this is a brand new guest.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "redeem_points",
            "description": (
                "Propose redeeming loyalty points, then redeem them after the guest confirms. "
                "Call once to get a summary, call again with the same arguments after the guest says yes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "member_number": {"type": "string"},
                    "last_name": {"type": "string"},
                    "points": {"type": "integer"},
                },
                "required": ["member_number", "last_name", "points"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_in",
            "description": (
                "Propose pre-arrival check-in for a booking, then complete it after the guest confirms. "
                "Call once to get a summary, call again with the same arguments after the guest says yes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {"type": "string"},
                    "last_name": {"type": "string"},
                    "arrival_time": {"type": "string", "description": "Expected arrival time, spoken form is fine."},
                    "special_requests": {"type": "string"},
                },
                "required": ["reference", "last_name", "arrival_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_preferences",
            "description": "Save the guest's stated preferences (dining, room, activities) for personalized recommendations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "preferences": {"type": "string"},
                    "first_name": {
                        "type": "string",
                        "description": "Guest's first name. Only needed if this is a brand new guest.",
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Guest's last name. Only needed if this is a brand new guest.",
                    },
                },
                "required": ["preferences"],
            },
        },
    },
]


def _resolve_guest_id(db, session: AgentSession, first_name: str | None, last_name: str | None):
    if session.guest_id is not None:
        return session.guest_id, None
    if first_name and last_name:
        guest = guest_service.create(db, first_name, last_name)
        return guest.id, None
    return None, {"error": "I need your name to do that."}


def _propose_or_execute(session: AgentSession, tool_name: str, args: dict, propose_fn: Callable, execute_fn: Callable) -> dict:
    pending = session.pending_action
    if pending is not None and pending.tool == tool_name and pending.args == args:
        session.pending_action = None
        return execute_fn(pending.args)
    result = propose_fn(args)
    if "error" in result:
        return result
    session.pending_action = PendingAction(tool=tool_name, args=args)
    return result


def _booking_dict(db, booking) -> dict:
    room_type = db.get(RoomType, booking.room_type_id)
    return {
        "reference": booking.reference,
        "room_type_code": room_type.code,
        "room_type_name": room_type.name,
        "check_in": booking.check_in_date.isoformat(),
        "check_out": booking.check_out_date.isoformat(),
        "num_guests": booking.num_guests,
        "status": booking.status,
        "total_price_paise": booking.total_price_paise,
        "special_requests": booking.special_requests,
    }


def _loyalty_dict(account) -> dict:
    return {
        "member_number": account.member_number,
        "tier": account.tier,
        "points_balance": account.points_balance,
    }


def _checkin_dict(checkin) -> dict:
    return {
        "booking_id": checkin.booking_id,
        "arrival_time": checkin.arrival_time,
        "status": checkin.status,
        "special_requests": checkin.special_requests,
    }


def check_availability(db, session: AgentSession, check_in: str, check_out: str, room_type_code: str | None = None) -> dict:
    try:
        options = booking_service.check_availability(
            db, date.fromisoformat(check_in), date.fromisoformat(check_out), room_type_code
        )
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {"options": options}


def create_booking(
    db,
    session: AgentSession,
    room_type_code: str,
    check_in: str,
    check_out: str,
    num_guests: int,
    special_requests: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict:
    args = dict(
        room_type_code=room_type_code,
        check_in=check_in,
        check_out=check_out,
        num_guests=num_guests,
        special_requests=special_requests,
        first_name=first_name,
        last_name=last_name,
    )

    def propose(a):
        try:
            options = booking_service.check_availability(
                db, date.fromisoformat(a["check_in"]), date.fromisoformat(a["check_out"]), a["room_type_code"]
            )
        except (ValueError, RuntimeError) as e:
            return {"error": str(e)}
        if not options:
            return {"error": "No availability for that room type and dates."}
        option = options[0]
        summary = (
            f"Book the {option['name']} from {a['check_in']} to {a['check_out']} for "
            f"{a['num_guests']} guest(s), total {option['total_price_paise']} paise. Confirm?"
        )
        return {"summary": summary, **option, "check_in": a["check_in"], "check_out": a["check_out"], "num_guests": a["num_guests"]}

    def execute(a):
        guest_id, error = _resolve_guest_id(db, session, a["first_name"], a["last_name"])
        if error:
            return error
        try:
            booking = booking_service.create_booking(
                db,
                guest_id,
                a["room_type_code"],
                date.fromisoformat(a["check_in"]),
                date.fromisoformat(a["check_out"]),
                a["num_guests"],
                a["special_requests"],
            )
        except (ValueError, RuntimeError) as e:
            return {"error": str(e)}
        session.guest_id = guest_id
        return _booking_dict(db, booking)

    return _propose_or_execute(session, "create_booking", args, propose, execute)


def find_booking(db, session: AgentSession, reference: str, last_name: str) -> dict:
    booking = booking_service.find_booking(db, reference, last_name)
    if booking is None:
        return {"error": "No booking found with that reference and last name."}
    session.guest_id = booking.guest_id
    return _booking_dict(db, booking)


def modify_booking(
    db,
    session: AgentSession,
    reference: str,
    last_name: str,
    room_type_code: str | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    num_guests: int | None = None,
    special_requests: str | None = None,
) -> dict:
    args = dict(
        reference=reference,
        last_name=last_name,
        room_type_code=room_type_code,
        check_in=check_in,
        check_out=check_out,
        num_guests=num_guests,
        special_requests=special_requests,
    )

    def propose(a):
        booking = booking_service.find_booking(db, a["reference"], a["last_name"])
        if booking is None:
            return {"error": "No booking found with that reference and last name."}
        if booking.status != BookingStatus.CONFIRMED:
            return {"error": "That booking is not confirmed."}
        room_type = db.get(RoomType, booking.room_type_id)
        new_code = a["room_type_code"] or room_type.code
        new_check_in = a["check_in"] or booking.check_in_date.isoformat()
        new_check_out = a["check_out"] or booking.check_out_date.isoformat()
        try:
            options = booking_service.check_availability(
                db, date.fromisoformat(new_check_in), date.fromisoformat(new_check_out), new_code
            )
        except (ValueError, RuntimeError) as e:
            return {"error": str(e)}
        if not options:
            return {"error": "No availability for the requested change."}
        option = options[0]
        summary = (
            f"Change booking {a['reference']} to {option['name']} from {new_check_in} to {new_check_out}, "
            f"new total {option['total_price_paise']} paise. Confirm?"
        )
        return {"summary": summary, **option, "check_in": new_check_in, "check_out": new_check_out}

    def execute(a):
        try:
            booking = booking_service.modify_booking(
                db,
                a["reference"],
                a["last_name"],
                a["room_type_code"],
                date.fromisoformat(a["check_in"]) if a["check_in"] else None,
                date.fromisoformat(a["check_out"]) if a["check_out"] else None,
                a["num_guests"],
                a["special_requests"],
            )
        except (ValueError, RuntimeError) as e:
            return {"error": str(e)}
        return _booking_dict(db, booking)

    return _propose_or_execute(session, "modify_booking", args, propose, execute)


def cancel_booking(db, session: AgentSession, reference: str, last_name: str) -> dict:
    args = dict(reference=reference, last_name=last_name)

    def propose(a):
        booking = booking_service.find_booking(db, a["reference"], a["last_name"])
        if booking is None:
            return {"error": "No booking found with that reference and last name."}
        if booking.status != BookingStatus.CONFIRMED:
            return {"error": "That booking is not confirmed."}
        room_type = db.get(RoomType, booking.room_type_id)
        summary = (
            f"Cancel booking {a['reference']} for the {room_type.name}, "
            f"{booking.check_in_date.isoformat()} to {booking.check_out_date.isoformat()}. Confirm?"
        )
        return {"summary": summary, "reference": a["reference"]}

    def execute(a):
        try:
            booking = booking_service.cancel_booking(db, a["reference"], a["last_name"])
        except (ValueError, RuntimeError) as e:
            return {"error": str(e)}
        return _booking_dict(db, booking)

    return _propose_or_execute(session, "cancel_booking", args, propose, execute)


def loyalty_status(db, session: AgentSession, member_number: str, last_name: str) -> dict:
    account = loyalty_service.get_status(db, member_number, last_name)
    if account is None:
        return {"error": "No loyalty account found with that member number and last name."}
    session.guest_id = account.guest_id
    return _loyalty_dict(account)


def enroll_loyalty(db, session: AgentSession, first_name: str | None = None, last_name: str | None = None) -> dict:
    args = dict(first_name=first_name, last_name=last_name)

    def propose(a):
        return {"summary": "Enroll you in the loyalty program as a Silver member with 0 points. Confirm?"}

    def execute(a):
        guest_id, error = _resolve_guest_id(db, session, a["first_name"], a["last_name"])
        if error:
            return error
        try:
            account = loyalty_service.enroll(db, guest_id)
        except (ValueError, RuntimeError) as e:
            return {"error": str(e)}
        session.guest_id = guest_id
        return _loyalty_dict(account)

    return _propose_or_execute(session, "enroll_loyalty", args, propose, execute)


def redeem_points(db, session: AgentSession, member_number: str, last_name: str, points: int) -> dict:
    args = dict(member_number=member_number, last_name=last_name, points=points)

    def propose(a):
        account = loyalty_service.get_status(db, a["member_number"], a["last_name"])
        if account is None:
            return {"error": "No loyalty account found with that member number and last name."}
        if account.points_balance < a["points"]:
            return {"error": "Insufficient points balance."}
        new_balance = account.points_balance - a["points"]
        summary = f"Redeem {a['points']} points, leaving a balance of {new_balance}. Confirm?"
        return {"summary": summary, "points": a["points"], "new_balance": new_balance}

    def execute(a):
        try:
            transaction = loyalty_service.redeem_points(db, a["member_number"], a["last_name"], a["points"])
        except (ValueError, RuntimeError) as e:
            return {"error": str(e)}
        return {"points_redeemed": a["points"], "points_delta": transaction.points_delta}

    return _propose_or_execute(session, "redeem_points", args, propose, execute)


def check_in(
    db,
    session: AgentSession,
    reference: str,
    last_name: str,
    arrival_time: str,
    special_requests: str | None = None,
) -> dict:
    args = dict(reference=reference, last_name=last_name, arrival_time=arrival_time, special_requests=special_requests)

    def propose(a):
        booking = booking_service.find_booking(db, a["reference"], a["last_name"])
        if booking is None:
            return {"error": "No booking found with that reference and last name."}
        if booking.status != BookingStatus.CONFIRMED:
            return {"error": "That booking is not confirmed."}
        summary = f"Check in booking {a['reference']} with arrival time {a['arrival_time']}. Confirm?"
        return {"summary": summary}

    def execute(a):
        try:
            checkin = checkin_service.check_in(db, a["reference"], a["last_name"], a["arrival_time"], a["special_requests"])
        except (ValueError, RuntimeError) as e:
            return {"error": str(e)}
        return _checkin_dict(checkin)

    return _propose_or_execute(session, "check_in", args, propose, execute)


def save_preferences(
    db, session: AgentSession, preferences: str, first_name: str | None = None, last_name: str | None = None
) -> dict:
    guest_id, error = _resolve_guest_id(db, session, first_name, last_name)
    if error:
        return error
    guest = guest_service.save_preferences(db, guest_id, preferences)
    session.guest_id = guest.id
    return {"guest_id": guest.id, "preferences": guest.preferences}


TOOL_HANDLERS: dict[str, Callable] = {
    "check_availability": check_availability,
    "create_booking": create_booking,
    "find_booking": find_booking,
    "modify_booking": modify_booking,
    "cancel_booking": cancel_booking,
    "loyalty_status": loyalty_status,
    "enroll_loyalty": enroll_loyalty,
    "redeem_points": redeem_points,
    "check_in": check_in,
    "save_preferences": save_preferences,
}
