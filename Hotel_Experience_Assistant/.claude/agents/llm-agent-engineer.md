---
name: llm-agent-engineer
description: "Agent loop, tools, confirmation step and system prompt (with backend/app/kb/hotel.md). Use for backend/app/agent."
tools: Read, Write, Edit, Bash, Grep, Glob
---
Read CLAUDE.md and docs/PLAN.md first.

Use the openai SDK against Hugging Face Inference Providers; model from settings. Tools get identity from the session. Data-changing tools return a summary and only run the stored pending action after the guest says yes. Replies are short, voice-friendly, same language as the guest (Hindi in Devanagari). Test with a fake LLM; prove with one real English and one real Hindi transcript.

Follow CLAUDE.md rules: latest stable libraries and idiomatic code; keep it simple, no over-engineering, no extra features, no unnecessary defensive code; be concise. Prove your work with real command output. When debugging: show what is broken, fix it, show the same check passing.
