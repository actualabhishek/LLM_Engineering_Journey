"""Proof that the deployed GPU worker works: calls the live HTTPS endpoints
(no import of modal_app.py), saves English and Hindi fixture audio, and
transcribes them back. Run with:

    uv run --with httpx python gpu_worker/test_worker.py
"""

import os
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "backend" / "tests" / "fixtures"

EN_TEXT = "Good evening, how can I help you today?"
HI_TEXT = "नमस्ते, मैं आपकी क्या मदद कर सकता हूँ?"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")

    worker_url = os.environ.get("GPU_WORKER_URL")
    worker_token = os.environ.get("GPU_WORKER_TOKEN")
    if not worker_url or not worker_token:
        sys.exit("Set GPU_WORKER_URL and GPU_WORKER_TOKEN (in .env or the environment) before running this script.")

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    en_path = FIXTURES_DIR / "en_sample.wav"
    hi_path = FIXTURES_DIR / "hi_sample.wav"

    client = httpx.Client(
        base_url=worker_url,
        headers={"Authorization": f"Bearer {worker_token}"},
        timeout=120.0,
    )

    checks_passed = []

    # 1. English /speak (cold if the worker was idle)
    start = time.perf_counter()
    resp = client.post("/speak", json={"text": EN_TEXT, "language": "en"})
    resp.raise_for_status()
    en_path.write_bytes(resp.content)
    elapsed = time.perf_counter() - start
    print(f"[1] /speak en (cold if worker was idle): {elapsed:.2f}s -> {en_path}")

    # 2. Hindi /speak (warm)
    start = time.perf_counter()
    resp = client.post("/speak", json={"text": HI_TEXT, "language": "hi"})
    resp.raise_for_status()
    hi_path.write_bytes(resp.content)
    elapsed = time.perf_counter() - start
    print(f"[2] /speak hi (warm): {elapsed:.2f}s -> {hi_path}")

    # 3. English /transcribe (warm)
    start = time.perf_counter()
    with en_path.open("rb") as f:
        resp = client.post("/transcribe", files={"audio": ("en_sample.wav", f, "audio/wav")})
    resp.raise_for_status()
    elapsed = time.perf_counter() - start
    data = resp.json()
    passed = "help" in data["text"].lower()
    checks_passed.append(passed)
    print(f"[3] /transcribe en (warm): {elapsed:.2f}s")
    print(f"    text={data['text']!r} language={data['language']} probability={data['language_probability']:.3f}")
    print(f"    {'PASS' if passed else 'FAIL'}: 'help' in transcript")

    # 4. Hindi /transcribe (warm)
    start = time.perf_counter()
    with hi_path.open("rb") as f:
        resp = client.post("/transcribe", files={"audio": ("hi_sample.wav", f, "audio/wav")})
    resp.raise_for_status()
    elapsed = time.perf_counter() - start
    data = resp.json()
    passed = "मदद" in data["text"]
    checks_passed.append(passed)
    print(f"[4] /transcribe hi (warm): {elapsed:.2f}s")
    print(f"    text={data['text']!r} language={data['language']} probability={data['language_probability']:.3f}")
    print(f"    {'PASS' if passed else 'FAIL'}: 'मदद' in transcript")

    if all(checks_passed):
        sys.exit(0)
    sys.exit("One or more keyword checks failed.")


if __name__ == "__main__":
    main()
