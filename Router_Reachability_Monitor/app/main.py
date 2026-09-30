"""FastAPI app: starts the monitor loop on startup, serves the dashboard + REST + WebSocket."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.alerts.callmebot import CallMeBotCallNotifier, CallMeBotWhatsAppNotifier
from app.alerts.daily import daily_summary_loop
from app.alerts.manager import AlertManager
from app.alerts.ntfy import NtfyNotifier
from app.alerts.telegram import TelegramNotifier
from app.alerts.telegram_bot import telegram_bot_loop
from app.config import Settings, load_settings
from app.db import get_db
from app.monitor.scheduler import monitor_loop
from app.monitor.state import StateMachine
from app.runtime import RuntimeState
from app.web.routes import protected, router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("/data") if Path("/data").is_dir() else Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "monitor.db"


async def build_runtime_state(settings: Settings) -> RuntimeState:
    conn = await get_db(DB_PATH)
    state_machine = StateMachine(
        settings.app.probe.fail_threshold,
        settings.app.probe.recover_threshold,
        settings.app.flap.max_changes,
        settings.app.flap.window_s,
    )
    secrets = settings.secrets
    notifiers = {
        "telegram": TelegramNotifier(secrets.telegram_bot_token, secrets.telegram_chat_id),
        "telegram_call": CallMeBotCallNotifier(secrets.callmebot_tg_user),
        "whatsapp": CallMeBotWhatsAppNotifier(secrets.callmebot_wa_phone, secrets.callmebot_wa_apikey),
        "ntfy": NtfyNotifier(secrets.ntfy_topic),
    }
    alert_manager = AlertManager(notifiers, settings.app.alerts.escalate_call_after_s, settings.app.alerts.repeat_every_s)
    return RuntimeState(settings=settings, conn=conn, state_machine=state_machine, alert_manager=alert_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    state = await build_runtime_state(settings)
    app.state.runtime = state

    tasks = [
        asyncio.create_task(monitor_loop(state)),
        asyncio.create_task(telegram_bot_loop(state)),
        asyncio.create_task(daily_summary_loop(state)),
    ]
    logger.info(
        "monitor loop started: %d targets, interval=%ds",
        len(settings.app.targets), settings.app.probe.interval_s,
    )

    yield

    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    await state.conn.close()
    logger.info("shutdown complete")


app = FastAPI(title="Router Reachability Monitor", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "web" / "static")), name="static")
app.include_router(router)
app.include_router(protected)
