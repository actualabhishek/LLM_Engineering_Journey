import json

from openai import OpenAI
from sqlalchemy.orm import Session

from app.agent.prompt import build_system_prompt
from app.agent.session import AgentSession
from app.agent.tools import TOOL_HANDLERS, TOOLS
from app.config import settings

MAX_TOOL_ROUNDS = 5


def build_client() -> OpenAI:
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)


def run_turn(client: OpenAI, db: Session, session: AgentSession, history: list[dict], user_message: str) -> str:
    history.append({"role": "user", "content": user_message})

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "system", "content": build_system_prompt()}] + history,
            tools=TOOLS,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            history.append({"role": "assistant", "content": message.content})
            return message.content

        history.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [tc.model_dump() for tc in message.tool_calls],
            }
        )
        for tool_call in message.tool_calls:
            handler = TOOL_HANDLERS[tool_call.function.name]
            kwargs = json.loads(tool_call.function.arguments)
            result = handler(db, session, **kwargs)
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                }
            )

    raise RuntimeError("agent exceeded MAX_TOOL_ROUNDS without a final reply")
