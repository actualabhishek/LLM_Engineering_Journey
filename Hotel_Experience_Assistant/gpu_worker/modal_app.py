import os
import secrets
from typing import Literal

import modal
from pydantic import BaseModel, Field

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("espeak-ng", "git")
    .pip_install(
        "fastapi[standard]",
        "torch==2.6.0",
        "torchaudio==2.6.0",
        "transformers==4.46.1",
        "faster-whisper==1.2.1",
        "kokoro==0.9.4",
        "soundfile==0.13.1",
        "huggingface-hub==0.28.1",
        "numpy",
        "git+https://github.com/huggingface/parler-tts.git",
    )
)

WHISPER_MODEL = "deepdml/faster-whisper-large-v3-turbo-ct2"
KOKORO_REPO = "hexgrad/Kokoro-82M"
PARLER_REPO = "ai4bharat/indic-parler-tts"


def download_models():
    from huggingface_hub import snapshot_download

    snapshot_download(WHISPER_MODEL)
    snapshot_download(KOKORO_REPO)
    snapshot_download(PARLER_REPO)  # gated model, needs HF_TOKEN from the secret


image = image.run_function(
    download_models,
    secrets=[modal.Secret.from_name("hotel-worker")],
)

app = modal.App("hotel-voice-worker", image=image)

DIVYA_DESCRIPTION = (
    "Divya's voice is monotone yet slightly fast in delivery, "
    "with a very close recording that almost has no background noise."
)


MAX_SPEAK_CHARS = 500  # one spoken sentence; replies are split sentence by sentence
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # ~60s of audio, generous for one utterance


class SpeakRequest(BaseModel):
    text: str = Field(max_length=MAX_SPEAK_CHARS)
    language: Literal["en", "hi"]


@app.cls(
    gpu="T4",
    scaledown_window=300,
    timeout=120,
    secrets=[modal.Secret.from_name("hotel-worker")],
)
class SpeechWorker:
    @modal.enter()
    def load_models(self):
        from faster_whisper import WhisperModel
        from kokoro import KPipeline
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer

        self.whisper = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
        self.kokoro = KPipeline(lang_code="a")  # American English

        self.device = "cuda"
        self.parler = ParlerTTSForConditionalGeneration.from_pretrained(PARLER_REPO).to(self.device)
        self.parler_tokenizer = AutoTokenizer.from_pretrained(PARLER_REPO)
        self.parler_description_tokenizer = AutoTokenizer.from_pretrained(
            self.parler.config.text_encoder._name_or_path
        )

    @modal.asgi_app()
    def web(self):
        import io

        import numpy as np
        import soundfile as sf
        from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
        from fastapi.responses import Response
        from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

        web_app = FastAPI()
        auth_scheme = HTTPBearer()

        def check_token(creds: HTTPAuthorizationCredentials = Depends(auth_scheme)):
            if not secrets.compare_digest(creds.credentials, os.environ["GPU_WORKER_TOKEN"]):
                raise HTTPException(status_code=401, detail="Invalid bearer token")

        @web_app.post("/transcribe")
        async def transcribe(audio: UploadFile = File(...), _: None = Depends(check_token)):
            if audio.size is not None and audio.size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Audio too large")
            data = await audio.read()
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Audio too large")
            segments, info = self.whisper.transcribe(io.BytesIO(data), beam_size=5)
            text = "".join(seg.text for seg in segments).strip()
            return {
                "text": text,
                "language": info.language,
                "language_probability": info.language_probability,
            }

        @web_app.post("/speak")
        def speak(body: SpeakRequest, _: None = Depends(check_token)):
            buffer = io.BytesIO()
            if body.language == "en":
                chunks = [audio for _, _, audio in self.kokoro(body.text, voice="af_heart")]
                audio = chunks[0] if len(chunks) == 1 else np.concatenate(chunks)
                sf.write(buffer, audio, 24000, format="WAV")
            else:
                desc = self.parler_description_tokenizer(DIVYA_DESCRIPTION, return_tensors="pt").to(self.device)
                prompt = self.parler_tokenizer(body.text, return_tensors="pt").to(self.device)
                generation = self.parler.generate(
                    input_ids=desc.input_ids,
                    attention_mask=desc.attention_mask,
                    prompt_input_ids=prompt.input_ids,
                    prompt_attention_mask=prompt.attention_mask,
                )
                audio = generation.cpu().numpy().squeeze()
                sf.write(buffer, audio, self.parler.config.sampling_rate, format="WAV")

            return Response(content=buffer.getvalue(), media_type="audio/wav")

        return web_app
