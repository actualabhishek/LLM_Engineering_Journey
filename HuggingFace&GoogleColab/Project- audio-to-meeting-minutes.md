# 🎙️ Audio-to-Meeting-Minutes Generator
### A Multimodal LLM Pipeline: Whisper ASR + Llama 3.2 3B (4-bit Quantized)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1eDBapYvHwvUF-AzZ4DHJz5G3hyTlfmdn#scrollTo=HS0rJQz-peMA)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Transformers](https://img.shields.io/badge/🤗%20Transformers-4.57.6-yellow.svg)
![GPU](https://img.shields.io/badge/GPU-Colab%20T4-orange.svg)
![Quantization](https://img.shields.io/badge/Quantization-4--bit%20NF4-green.svg)

**Run it live:** https://colab.research.google.com/drive/1eDBapYvHwvUF-AzZ4DHJz5G3hyTlfmdn#scrollTo=HS0rJQz-peMA

---

## 📌 Overview

This project builds an end-to-end **speech-to-structured-document pipeline** that takes a raw audio recording of a council meeting and automatically produces professional, well-formatted **meeting minutes** — complete with summary, discussion points, takeaways, and action items with owners.

It chains together two distinct model classes into a single workflow:

1. **Automatic Speech Recognition (ASR)** — `openai/whisper-medium.en` transcribes the spoken audio into raw text.
2. **Instruction-Tuned LLM Generation** — `meta-llama/Llama-3.2-3B-Instruct`, loaded in 4-bit precision, consumes that transcript and reasons over it to produce structured, human-readable minutes in Markdown.

This is a practical demonstration of **multimodal orchestration** — using one model's output as another model's input — a pattern that underlies real-world AI agent and document-automation systems.

---

## 🏗️ Architecture

```
 Audio File (.mp3)
      │
      ▼
┌─────────────────────────────┐
│  Whisper Medium (EN)         │   ASR — Speech → Text
│  torch.float16, CUDA          │
└─────────────────────────────┘
      │  transcription (text)
      ▼
┌─────────────────────────────┐
│  Prompt Construction          │   System + User message
│  (Chat Template)              │   with structured instructions
└─────────────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│  Llama 3.2 3B Instruct        │   4-bit NF4 Quantized (BitsAndBytes)
│  Streamed Generation          │   Text → Markdown Minutes
└─────────────────────────────┘
      │
      ▼
  Rendered Markdown Minutes
  (Summary, Discussion, Takeaways, Action Items)
```

---

## ⚙️ Tech Stack

| Component | Technology |
|---|---|
| **Environment** | Google Colab (Free Tier — T4 GPU) |
| **ASR Model** | `openai/whisper-medium.en` (HuggingFace `pipeline`) |
| **LLM** | `meta-llama/Llama-3.2-3B-Instruct` |
| **Quantization** | BitsAndBytes 4-bit NF4, double quantization, `bfloat16` compute dtype |
| **Core Libraries** | `transformers==4.57.6`, `accelerate`, `bitsandbytes`, `torch` |
| **Storage** | Google Drive mount for audio input |
| **Auth** | HuggingFace Hub token via Colab secrets (`userdata`) |
| **Output Rendering** | IPython `display(Markdown(...))` for in-notebook rich output |
| **Streaming** | `TextStreamer` for real-time token-by-token generation feedback |

---

## 🚀 What This Project Demonstrates

- **Multimodal pipeline design** — chaining an ASR model and an LLM into a single coherent workflow, where the output of one model becomes structured input to the next.
- **Memory-efficient LLM inference on free-tier hardware** — running a 3B-parameter instruction-tuned model on a single Colab T4 GPU by applying **4-bit NF4 quantization** with double quantization, keeping VRAM usage low without a dedicated paid GPU tier.
- **Prompt engineering for structured document generation** — a system + user message design that reliably constrains the LLM to produce Markdown-formatted minutes with a specific schema (summary → discussion points → takeaways → action items with owners), rather than free-form prose.
- **Chat-template-based inference** — using `tokenizer.apply_chat_template()` for correctly formatted multi-turn prompts instead of manually stitching special tokens.
- **Real-time generation feedback** — integrating `TextStreamer` so tokens render as they're generated, useful for debugging and demoing to non-technical stakeholders.
- **Secure credential handling in Colab** — HuggingFace authentication via `userdata.get()` secrets rather than hardcoded tokens, plus Google Drive mounting for private audio file access.
- **Practical automation use case** — this pipeline mirrors a real enterprise need (auto-generating minutes from recorded council/board/ops meetings), directly relevant to the kind of automation-for-the-enterprise projects in this portfolio (e.g. Network Ops Daily Standup bot, Roster Maker agent).

---

## 📝 Pipeline Walkthrough

1. **Environment setup** — install pinned versions of `transformers`, `bitsandbytes`, and `accelerate` for compatibility.
2. **Mount Google Drive** — access the source audio file (`denver_extract.mp3`) stored privately in Drive.
3. **Authenticate with HuggingFace** — log in using a Colab secret token to access gated models like Llama 3.2.
4. **Transcribe audio** — run the Whisper ASR pipeline on GPU (`float16`) with timestamp return enabled, producing a clean text transcription of the council meeting.
5. **Construct the prompt** — build a system message defining the assistant's role (minutes-writer) and a user message embedding the transcript with explicit formatting instructions.
6. **Load Llama 3.2 3B Instruct in 4-bit** — configure `BitsAndBytesConfig` for NF4 quantization with double quantization and `bfloat16` compute, then load the model with `device_map="auto"`.
7. **Generate with streaming** — apply the chat template, generate up to 2000 new tokens with `TextStreamer` for live output, then decode and render the final Markdown minutes in-notebook.

---

## 📄 Sample Output Structure

The generated minutes follow this schema:

```markdown
# Denver Council Meeting — Minutes

**Date:** [extracted/inferred]
**Location:** [extracted/inferred]
**Attendees:** [extracted/inferred]

## Summary
...

## Discussion Points
- ...

## Takeaways
- ...

## Action Items
| Action | Owner |
|---|---|
| ... | ... |
```

---

## 🔮 Possible Extensions

- Swap Whisper for `whisper-large-v3` or a diarization-enabled variant to attribute discussion points to specific speakers.
- Add a Gradio front-end for drag-and-drop audio upload → one-click minutes generation.
- Push generated minutes directly to a SharePoint/Drive folder or Slack/Teams channel as a downstream automation step (similar in spirit to the Roster Maker and Network Ops Standup bot projects).
- Batch-process multiple meeting recordings and auto-generate a searchable minutes archive.

---

## 🔗 Notebook

**Google Colab:** https://colab.research.google.com/drive/1eDBapYvHwvUF-AzZ4DHJz5G3hyTlfmdn#scrollTo=HS0rJQz-peMA

**Hardware used:** Google Colab Free Tier — NVIDIA T4 GPU

---

*Part of the [`llm-engineering-journey`](https://github.com/) portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.*
