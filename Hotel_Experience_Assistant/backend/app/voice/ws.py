import json
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.agent.loop import build_client, run_turn
from app.agent.session import AgentSession
from app.db import SessionLocal
from app.models import Conversation, Message
from app.voice import normalize, sentences, worker_client

logger = logging.getLogger(__name__)

router = APIRouter()

GREETING = "Namaste! Welcome to Sundar Vista Hotel. How can I help you today?"

MUTATING_TOOLS = {
    "create_booking",
    "modify_booking",
    "cancel_booking",
    "enroll_loyalty",
    "redeem_points",
    "check_in",
}

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def _reply_language(text: str) -> str:
    return "hi" if _DEVANAGARI_RE.search(text) else "en"


async def _speak_sentences(ws: WebSocket, reply: str, language: str) -> None:
    for sentence in sentences.split_sentences(reply):
        spoken = normalize.to_hindi_speech_text(sentence) if language == "hi" else sentence
        await ws.send_json({"type": "caption", "role": "assistant", "text": sentence})
        audio = await worker_client.speak(spoken, language)
        await ws.send_bytes(audio)


def _tool_name_for_call(history: list[dict], tool_call_id: str) -> str | None:
    for entry in history:
        if entry["role"] != "assistant" or not entry.get("tool_calls"):
            continue
        for tc in entry["tool_calls"]:
            if tc["id"] == tool_call_id:
                return tc["function"]["name"]
    return None


async def _send_cards(ws: WebSocket, history: list[dict], since: int) -> None:
    for entry in history[since:]:
        if entry["role"] != "tool":
            continue
        name = _tool_name_for_call(history, entry["tool_call_id"])
        if name not in MUTATING_TOOLS:
            continue
        result = json.loads(entry["content"])
        if "error" in result or "summary" in result:
            continue
        await ws.send_json({"type": "card", "tool": name, "data": result})


@router.websocket("/ws/voice")
async def voice_ws(ws: WebSocket) -> None:
    await ws.accept()
    db = SessionLocal()
    session = AgentSession()
    client = build_client()
    history: list[dict] = []

    conversation = Conversation()
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    try:
        await ws.send_json({"type": "caption", "role": "assistant", "text": GREETING})
        await ws.send_bytes(await worker_client.speak(GREETING, "en"))

        while True:
            audio_bytes = await ws.receive_bytes()
            try:
                transcript_result = await worker_client.transcribe(audio_bytes)
                transcript = transcript_result["text"]
                await ws.send_json({"type": "caption", "role": "guest", "text": transcript})

                db.add(Message(conversation_id=conversation.id, role="guest", content=transcript))
                db.commit()

                history_len = len(history)
                reply = await run_in_threadpool(run_turn, client, db, session, history, transcript)

                db.add(Message(conversation_id=conversation.id, role="assistant", content=reply))
                if session.guest_id is not None and conversation.guest_id is None:
                    conversation.guest_id = session.guest_id
                db.commit()

                language = _reply_language(reply)
                await _speak_sentences(ws, reply, language)
                await _send_cards(ws, history, history_len)
            except Exception:
                logger.exception("voice turn failed")
                await ws.send_json({"type": "error", "message": "Sorry, something went wrong. Please try again."})
    except WebSocketDisconnect:
        pass
    finally:
        conversation.ended_at = datetime.now(timezone.utc)
        db.commit()
        db.close()
