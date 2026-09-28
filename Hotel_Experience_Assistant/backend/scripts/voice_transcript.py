"""Real end-to-end proof of Phase 5: runs the actual FastAPI app (uvicorn, in
a background thread), connects to /ws/voice, and streams the English and
Hindi fixture recordings as guest utterances. Calls the real deployed GPU
worker (STT + TTS) and the real OpenRouter LLM. Run with:

    cd backend && uv run python -m scripts.voice_transcript
"""

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import websockets

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "backend" / "tests" / "fixtures"
SCRATCH_DIR = Path(tempfile.gettempdir()) / "hotel_assistant_voice_transcript"
PORT = 8931


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv(REPO_ROOT / ".env")

_DB_PATH = Path(tempfile.gettempdir()) / "hotel_assistant_voice_transcript.db"
if _DB_PATH.exists():
    _DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"

import uvicorn  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


def check(label: str, condition: bool) -> None:
    print(f"    {'PASS' if condition else 'FAIL'}: {label}")


async def collect(ws, first_timeout: float, idle_timeout: float) -> tuple[list[dict], list[bytes]]:
    captions: list[dict] = []
    audio_frames: list[bytes] = []
    timeout = first_timeout
    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except TimeoutError:
            break
        timeout = idle_timeout
        if isinstance(msg, bytes):
            audio_frames.append(msg)
            print(f"    <- audio frame, {len(msg)} bytes")
        else:
            data = json.loads(msg)
            print(f"    <- {data}")
            captions.append(data)
    return captions, audio_frames


async def run_turn(ws, label: str, audio_path: Path, index: int) -> bool:
    print(f"\n[{label}] sending {audio_path.name} ({audio_path.stat().st_size} bytes)")
    await ws.send(audio_path.read_bytes())
    captions, audio_frames = await collect(ws, first_timeout=120.0, idle_timeout=20.0)

    for i, frame in enumerate(audio_frames):
        out_path = SCRATCH_DIR / f"{label.lower()}_reply_{index}_{i}.wav"
        out_path.write_bytes(frame)
        print(f"    saved {out_path} ({len(frame)} bytes)")

    ok = len(captions) > 0 and len(audio_frames) > 0
    check(f"{label}: got at least one caption and one audio frame back", ok)
    return ok


async def main_async() -> bool:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    uri = f"ws://127.0.0.1:{PORT}/ws/voice"

    async with websockets.connect(uri, max_size=None, ping_interval=None) as ws:
        print("[connect] waiting for greeting...")
        greeting_captions, greeting_audio = await collect(ws, first_timeout=90.0, idle_timeout=10.0)
        greeting_ok = len(greeting_captions) > 0 and len(greeting_audio) > 0
        check("greeting: got a caption and an audio frame", greeting_ok)

        en_ok = await run_turn(ws, "English", FIXTURES_DIR / "en_sample.wav", 1)
        hi_ok = await run_turn(ws, "Hindi", FIXTURES_DIR / "hi_sample.wav", 2)

    return greeting_ok and en_ok and hi_ok


def wait_for_server() -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=1.0).raise_for_status()
            return
        except httpx.HTTPError:
            time.sleep(0.5)
    sys.exit("Server did not start in time.")


def main() -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        sys.exit("OPENROUTER_API_KEY not set (check .env at the repo root).")
    if not os.environ.get("GPU_WORKER_URL") or not os.environ.get("GPU_WORKER_TOKEN"):
        sys.exit("GPU_WORKER_URL / GPU_WORKER_TOKEN not set (check .env at the repo root).")

    Base.metadata.create_all(bind=engine)

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()
    wait_for_server()
    print(f"[server] up at http://127.0.0.1:{PORT}")

    try:
        passed = asyncio.run(main_async())
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        engine.dispose()
        _DB_PATH.unlink(missing_ok=True)

    if passed:
        print("\nAll checks passed.")
        sys.exit(0)
    sys.exit("One or more checks failed.")


if __name__ == "__main__":
    main()
