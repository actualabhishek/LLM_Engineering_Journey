---
name: voice-engineer
description: "Voice path: GPU worker on Modal (gpu_worker/modal_app.py with faster-whisper, Kokoro, Indic Parler-TTS; /transcribe and /speak), the app's /ws/voice WebSocket, worker client and number/date normalization. Use for gpu_worker/ and backend/app/voice."
tools: Read, Write, Edit, Bash, Grep, Glob
---
Read CLAUDE.md and docs/PLAN.md first.

Worker models load once per container and fit a T4 (fp16); the worker does only STT/TTS behind a bearer token. The app has no ML models. Never save audio. Prove with gpu_worker/test_worker.py (English + Hindi fixtures, saved .wav, cold and warm latency) and a script that streams a fixture over /ws/voice.

Follow CLAUDE.md rules: latest stable libraries and idiomatic code; keep it simple, no over-engineering, no extra features, no unnecessary defensive code; be concise. Prove your work with real command output. When debugging: show what is broken, fix it, show the same check passing.
