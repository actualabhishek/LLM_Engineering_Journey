import json
import logging
import os
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "inclusionai/ling-3.0-flash-vl:free"

ACTION_SCHEMA = """Respond with ONLY a JSON object (no markdown fences), matching this shape:
{
  "reply": "<short natural-language reply to show the user>",
  "actions": [
    {"type": "create_card", "column": "<column key>", "ticket_id": "<PREFIX-NUMBER>", "title": "...", "category": "Network|Security|Incident|Access|Planning", "priority": "P1" | "P2" | null, "assignee": "<initials>", "due_date": "YYYY-MM-DD"},
    {"type": "edit_card", "ticket_id": "<existing ticket id>", "title": "...", "category": "...", "priority": "...", "assignee": "...", "due_date": "..."},
    {"type": "move_card", "ticket_id": "<existing ticket id>", "column": "<column key>"},
    {"type": "rename_column", "column": "<column key>", "title": "<new title>"}
  ]
}
Only include fields you are actually changing on edit_card. If the message doesn't call for any board change (small talk, a question, unclear request), return an empty actions list.
Choose a new ticket_id for create_card by continuing the existing numbering for that prefix (CHG-, INC-, TASK-)."""


def build_system_prompt(board_name: str, columns: list[dict], cards: list[dict]) -> str:
    column_lines = "\n".join(f"- {c['key']}: {c['title']}" for c in columns)
    card_lines = "\n".join(
        f"- {c['ticket_id']} ({c['column_key']}): \"{c['title']}\" category={c['category']} "
        f"priority={c['priority']} assignee={c['assignee']} due={c['due_date']}"
        for c in cards
    )
    return (
        f"You are an assistant embedded in the Kanban board \"{board_name}\".\n"
        f"Today's date is {date.today().isoformat()}.\n\n"
        f"Columns (key: title):\n{column_lines}\n\n"
        f"Cards:\n{card_lines or '(no cards)'}\n\n"
        f"You can create, edit, move cards, and rename columns.\n{ACTION_SCHEMA}"
    )


async def get_chat_response(
    message: str, board_name: str, columns: list[dict], cards: list[dict]
) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    fallback = {"reply": "Sorry, I couldn't process that right now.", "actions": []}
    if not api_key:
        return fallback

    system_prompt = build_system_prompt(board_name, columns, cards)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        detail = getattr(getattr(exc, "response", None), "text", "") or str(exc)
        logger.warning("OpenRouter call failed: %s", detail[:300])
        return fallback

    reply = parsed.get("reply")
    actions = parsed.get("actions")
    if not isinstance(reply, str) or not isinstance(actions, list):
        return fallback
    return {"reply": reply, "actions": actions}
