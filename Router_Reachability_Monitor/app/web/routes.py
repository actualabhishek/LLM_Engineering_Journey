"""REST + WebSocket routes. Dashboard, status/history/events APIs, mute, test alerts, healthz.

Every route requires login except /healthz (CLAUDE.md security rule: login is mandatory for
every page, API and WebSocket except /healthz).
"""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.alerts.base import Alert
from app.db import get_events, get_history
from app.runtime import RuntimeState
from app.web.auth import require_auth, require_auth_ws

router = APIRouter()  # public: only /healthz
protected = APIRouter(dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

RANGE_MULTIPLIERS = {"m": 60, "h": 3600, "d": 86400}


def _state(request: Request) -> RuntimeState:
    return request.app.state.runtime


@protected.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    state = _state(request)
    return templates.TemplateResponse(request, "index.html", {"site": state.settings.app.site})


@protected.get("/api/status")
async def api_status(request: Request) -> dict:
    return _state(request).status_snapshot()


@protected.get("/api/history")
async def api_history(request: Request, target: str, range: str = "1h") -> list[dict]:
    state = _state(request)
    since = int(time.time() - _parse_range(range))
    rows = await get_history(state.conn, target, since)
    return [dict(r) for r in rows]


@protected.get("/api/events")
async def api_events(request: Request, limit: int = 100) -> list[dict]:
    rows = await get_events(_state(request).conn, limit)
    return [dict(r) for r in rows]


@protected.post("/api/targets/{target_id}/mute")
async def mute_target(request: Request, target_id: str, minutes: int = 60) -> dict:
    state = _state(request)
    until = time.time() + minutes * 60
    state.muted_targets[target_id] = until
    return {"ok": True, "target_id": target_id, "muted_until": until}


@protected.delete("/api/targets/{target_id}/mute")
async def unmute_target(request: Request, target_id: str) -> dict:
    state = _state(request)
    was_muted = state.muted_targets.pop(target_id, None) is not None
    return {"ok": True, "target_id": target_id, "was_muted": was_muted}


@protected.post("/api/alerts/test")
async def test_alerts(request: Request) -> dict[str, bool]:
    state = _state(request)
    alert = Alert(target_id="test", hostname="TEST-ALERT", ip="0.0.0.0", new_state="DOWN", ts=time.time())
    # reuse AlertManager._send: same timeout + try/except wrapping as a real alert (CLAUDE.md rule 5)
    results = {name: await state.alert_manager._send(name, alert) for name in state.alert_manager.notifiers}
    return results


@protected.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    if not await require_auth_ws(websocket):
        return
    state: RuntimeState = websocket.app.state.runtime
    await websocket.accept()
    state.websockets.add(websocket)
    try:
        await websocket.send_json(state.status_snapshot())
        while True:
            await websocket.receive_text()  # client sends nothing meaningful yet; just detect disconnect
    except WebSocketDisconnect:
        pass
    finally:
        state.websockets.discard(websocket)


@router.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


def _parse_range(range_str: str) -> int:
    unit = range_str[-1]
    value = int(range_str[:-1])
    return value * RANGE_MULTIPLIERS.get(unit, 3600)
