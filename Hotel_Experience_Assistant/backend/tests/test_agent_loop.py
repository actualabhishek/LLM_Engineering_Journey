import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.agent.loop import MAX_TOOL_ROUNDS, run_turn
from app.agent.session import AgentSession
from app.models import Booking, BookingStatus, Guest

TODAY = date.today()


# ---------------------------------------------------------------------------
# Minimal fake OpenAI client: only what loop.py reads.
# ---------------------------------------------------------------------------


class FakeToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict):
        self.id = call_id
        self.function = _FakeFunction(name, json.dumps(arguments))

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.function.name, "arguments": self.function.arguments},
        }


class _FakeFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class FakeMessage:
    def __init__(self, content: str | None = None, tool_calls: list[FakeToolCall] | None = None):
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, message: FakeMessage):
        self.message = message


class FakeResponse:
    def __init__(self, message: FakeMessage):
        self.choices = [FakeChoice(message)]


class FakeClient:
    """Exposes .chat.completions.create like the openai SDK. `responses` is a
    list of FakeMessage, consumed one per call to `create`."""

    def __init__(self, responses: list[FakeMessage]):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self

    def create(self, model, messages, tools):
        self.calls.append({"model": model, "messages": messages, "tools": tools})
        return FakeResponse(self._responses.pop(0))


# ---------------------------------------------------------------------------


def _asha_booking(db):
    guest = db.scalar(select(Guest).where(Guest.last_name == "Rao"))
    return db.scalar(select(Booking).where(Booking.guest_id == guest.id))


def test_single_turn_no_tool_calls(seeded_db):
    client = FakeClient([FakeMessage(content="Hello, how can I help?")])
    session = AgentSession()
    history: list[dict] = []

    reply = run_turn(client, seeded_db, session, history, "Hi there")

    assert reply == "Hello, how can I help?"
    assert history == [
        {"role": "user", "content": "Hi there"},
        {"role": "assistant", "content": "Hello, how can I help?"},
    ]
    assert len(client.calls) == 1
    assert client.calls[0]["messages"][0]["role"] == "system"
    assert client.calls[0]["messages"][1:] == [{"role": "user", "content": "Hi there"}]


def test_turn_with_read_only_tool_round_trip(seeded_db):
    ci, co = (TODAY + timedelta(days=1)).isoformat(), (TODAY + timedelta(days=3)).isoformat()
    tool_call = FakeToolCall("call_1", "check_availability", {"check_in": ci, "check_out": co})
    client = FakeClient(
        [
            FakeMessage(tool_calls=[tool_call]),
            FakeMessage(content="We have rooms available for those dates."),
        ]
    )
    session = AgentSession()
    history: list[dict] = []

    reply = run_turn(client, seeded_db, session, history, "Any rooms free next week?")

    assert reply == "We have rooms available for those dates."
    assert len(client.calls) == 2
    # history accumulates: user, assistant(tool_calls), tool result, final assistant reply
    assert history[0] == {"role": "user", "content": "Any rooms free next week?"}
    assert history[1]["role"] == "assistant"
    assert history[1]["tool_calls"][0]["function"]["name"] == "check_availability"
    assert history[2]["role"] == "tool"
    assert history[2]["tool_call_id"] == "call_1"
    result = json.loads(history[2]["content"])
    assert "options" in result
    assert history[3] == {"role": "assistant", "content": "We have rooms available for those dates."}
    # second call to the model includes the growing history after the system prompt
    assert client.calls[1]["messages"][1:] == history[:3]


def test_propose_confirm_cycle_through_loop_cancels_booking(seeded_db):
    booking = _asha_booking(seeded_db)
    args = {"reference": booking.reference, "last_name": "Rao"}
    propose_call = FakeToolCall("call_propose", "cancel_booking", args)
    confirm_call = FakeToolCall("call_confirm", "cancel_booking", args)
    client = FakeClient(
        [
            FakeMessage(tool_calls=[propose_call]),
            FakeMessage(content="I'll cancel that booking, shall I go ahead?"),
            FakeMessage(tool_calls=[confirm_call]),
            FakeMessage(content="Done, your booking is cancelled."),
        ]
    )
    session = AgentSession()
    history: list[dict] = []

    first_reply = run_turn(client, seeded_db, session, history, "Please cancel my booking, reference and last name Rao")
    seeded_db.refresh(booking)
    assert booking.status == BookingStatus.CONFIRMED  # not yet, still just proposed
    assert first_reply == "I'll cancel that booking, shall I go ahead?"
    assert session.pending_action is not None

    second_reply = run_turn(client, seeded_db, session, history, "Yes, please go ahead")
    seeded_db.refresh(booking)

    assert second_reply == "Done, your booking is cancelled."
    assert booking.status == BookingStatus.CANCELLED
    assert session.pending_action is None


def test_exceeding_max_tool_rounds_raises(seeded_db):
    ci, co = (TODAY + timedelta(days=1)).isoformat(), (TODAY + timedelta(days=3)).isoformat()
    responses = [
        FakeMessage(tool_calls=[FakeToolCall(f"call_{i}", "check_availability", {"check_in": ci, "check_out": co})])
        for i in range(MAX_TOOL_ROUNDS)
    ]
    client = FakeClient(responses)
    session = AgentSession()
    history: list[dict] = []

    with pytest.raises(RuntimeError):
        run_turn(client, seeded_db, session, history, "Keep checking forever")
