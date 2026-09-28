import httpx

from app.config import settings

TIMEOUT = 90.0  # worker cold start can take ~60s


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.gpu_worker_url,
        headers={"Authorization": f"Bearer {settings.gpu_worker_token}"},
        timeout=TIMEOUT,
    )


async def transcribe(audio_bytes: bytes) -> dict:
    async with _client() as client:
        response = await client.post("/transcribe", files={"audio": ("utterance.wav", audio_bytes, "audio/wav")})
    response.raise_for_status()
    return response.json()


async def speak(text: str, language: str) -> bytes:
    async with _client() as client:
        response = await client.post("/speak", json={"text": text, "language": language})
    response.raise_for_status()
    return response.content
