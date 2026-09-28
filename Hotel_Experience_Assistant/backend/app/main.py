from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.config import settings
from app.voice.ws import router as voice_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

if not settings.secret_key:
    raise RuntimeError("SECRET_KEY must be set (see .env.example) - an empty key lets anyone forge admin session cookies")

app = FastAPI(title="Hotel Experience Assistant")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, https_only=True)
app.include_router(health_router)
app.include_router(voice_router)
app.include_router(admin_router)

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
