import secrets
import time
from typing import Optional

from fastapi import Header, HTTPException, status

SESSION_TTL_SECONDS = 24 * 60 * 60

_sessions: dict[str, dict] = {}


def create_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    _sessions[token] = {"user_id": user_id, "expires_at": time.time() + SESSION_TTL_SECONDS}
    return token


def _resolve_token(token: str) -> Optional[int]:
    session = _sessions.get(token)
    if session is None:
        return None
    if session["expires_at"] < time.time():
        del _sessions[token]
        return None
    return session["user_id"]


def require_user(authorization: str | None = Header(default=None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = _resolve_token(authorization.removeprefix("Bearer "))
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user_id
