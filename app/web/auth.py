"""HTTP Basic Auth for the dashboard. Every page/API/WS except /healthz needs it (CLAUDE.md security rule).

Failed attempts are rate-limited per client IP: an in-memory sliding window is enough here -
this is a single-process app with no shared state across instances.
"""
from __future__ import annotations

import secrets
import time
from collections import defaultdict

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

MAX_ATTEMPTS = 5
LOCKOUT_S = 300

_failed_attempts: dict[str, list[float]] = defaultdict(list)


def _is_locked_out(ip: str, now: float) -> bool:
    recent = [t for t in _failed_attempts[ip] if now - t < LOCKOUT_S]
    _failed_attempts[ip] = recent
    return len(recent) >= MAX_ATTEMPTS


def _check_credentials(username: str, password: str, dashboard_user: str, dashboard_pass: str) -> bool:
    if not dashboard_user or not dashboard_pass:
        return False  # login is mandatory - refuse to authenticate against an unconfigured/blank account
    valid_user = secrets.compare_digest(username, dashboard_user)
    valid_pass = secrets.compare_digest(password, dashboard_pass)
    return valid_user and valid_pass


def require_auth(request: Request, credentials: HTTPBasicCredentials = Depends(security)) -> str:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    if _is_locked_out(ip, now):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed login attempts, try again later")

    dash = request.app.state.runtime.settings.secrets
    if not _check_credentials(credentials.username, credentials.password, dash.dashboard_user, dash.dashboard_pass):
        _failed_attempts[ip].append(now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials", {"WWW-Authenticate": "Basic"})

    return credentials.username


async def require_auth_ws(websocket: WebSocket) -> bool:
    """WebSocket handshakes don't go through the HTTPBasic dependency machinery - check manually."""
    ip = websocket.client.host if websocket.client else "unknown"
    now = time.time()
    if _is_locked_out(ip, now):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return False

    auth_header = websocket.headers.get("authorization", "")
    username, password = _parse_basic_auth(auth_header)
    dash = websocket.app.state.runtime.settings.secrets
    if not _check_credentials(username, password, dash.dashboard_user, dash.dashboard_pass):
        _failed_attempts[ip].append(now)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return False

    return True


def _parse_basic_auth(header: str) -> tuple[str, str]:
    import base64

    if not header.startswith("Basic "):
        return "", ""
    try:
        decoded = base64.b64decode(header[len("Basic ") :]).decode("utf-8")
        username, _, password = decoded.partition(":")
        return username, password
    except (ValueError, UnicodeDecodeError):
        return "", ""
