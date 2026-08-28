<div align="center">
# 🚀 LLM Engineering Journey
 
### From Network Engineer to AI Engineer
*A documented, code-first journey through LLMs, agents, and applied AI automation.*
 
[![Jupyter Notebook](https://img.shields.io/badge/Jupyter-100%25-orange?logo=jupyter)](https://jupyter.org)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![HuggingFace](https://img.shields.io/badge/🤗-Transformers-yellow)](https://huggingface.co)
[![Colab](https://img.shields.io/badge/Google-Colab-F9AB00?logo=googlecolab)](https://colab.research.google.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
 
</div>
---
 
## 👋 About This Repo
 
I'm Abhishek — a Senior Network Engineer and Team Lead with 16+ years in enterprise infrastructure (F5 BIG-IP, Cisco Nexus, Palo Alto, Meraki, SD-WAN) for clients including Citi Group and British Petroleum. This repository documents my hands-on, code-first transition into **AI/ML Engineering** — not as a career change, but as an extension of two decades of systems thinking applied to a new class of infrastructure: large language models.
 
Every notebook here is real, run, and documented — not copied tutorials. The goal is depth over breadth: understand what's happening inside the model, not just call an API.
 
**How I work:** code-first, hands-on, run-the-cell-and-inspect-the-output learning. Every notebook includes Markdown documentation of what was learned and why, following a consistent naming and structure convention.
 
---
 
## 📂 Repository Structure
 
```
LLM_Engineering_Journey/
├── llm_fundamentals/            # Core concepts: tokenizers, transformer internals,
│                                 # attention mechanisms, MLP/feed-forward blocks
│
├── HuggingFace&GoogleColab/      # Applied HuggingFace + Colab notebooks:
│                                 # model loading, quantization, NLP pipelines,
│                                 # multimodal generation (audio, image, speech)
│
├── .gitignore
└── README.md
```
 
---
 
## 🧠 What's Inside
 
### 1. LLM Fundamentals
Foundational, from-first-principles notebooks covering:
- Transformer internals — attention mechanisms, MLP / feed-forward blocks
- Tokenization and how models actually "see" text
- Core building blocks before jumping into applied pipelines
### 2. HuggingFace & Google Colab — Applied Projects
Hands-on notebooks built and run on Google Colab (free-tier T4 GPU), covering:
 
| Area | What It Covers |
|---|---|
| **Model Loading & Quantization** | Comparing open-source model families — Llama, Phi, Gemma, Qwen, DeepSeek — with 4-bit NF4 quantization via BitsAndBytes |
| **NLP Pipelines** | Sentiment analysis, NER, question answering, summarization, translation, zero-shot classification |
| **Multimodal Generation** | Image generation (SDXL pipelines), text-to-speech (SpeechT5) |
| **Audio → Structured Text** | Whisper ASR + Llama 3.2 3B pipeline that transcribes meeting audio and generates structured Markdown minutes (summary, discussion points, action items with owners) |
| **Synthetic Data Generation** | Schema-constrained synthetic dataset generation using sampled decoding (temperature/top-p) and defensive JSON parsing |
| **Gradio Apps** | Dataset Generator (Llama 3.1 8B), streaming AI tutor (OpenAI), multi-persona AI debate simulator (GPT-4o-mini, Claude, Llama via Ollama) |
 
Each notebook follows a consistent format: **Markdown documentation cells + inline observations** after every meaningful code block, so the notebook itself is a record of what was learned, not just what was run.
 
---
 
## 🛠️ Tech Stack
 
- **Frameworks:** 🤗 Transformers, PyTorch, BitsAndBytes, Accelerate
- **Models:** Llama (3.1 / 3.2), Phi, Gemma, Qwen, DeepSeek, Whisper, SDXL, SpeechT5
- **Tools:** Google Colab (T4 GPU), Gradio, Hugging Face Hub
- **APIs:** Anthropic Claude, OpenAI
- **Techniques:** 4-bit NF4 quantization, chat-template prompting, streaming generation, prompt engineering for structured output, schema-constrained synthetic data generation
---
 
## 🗺️ Broader Portfolio Roadmap
 
This repo is one part of a larger applied-AI portfolio built alongside my day-to-day network engineering role. Related tracks (documented separately, referenced here for context):
 
- 🤖 **Network AI Agents** — Copilot Studio Roster Maker agent, Network Ops Daily Standup bot (Power Automate + Dataverse)
- 📈 **ForexAI Trader** — leading-indicator signal engine (RSI divergence, retest entries) with an LLM-based validator/veto layer
- 📊 **NIFTY 50 Options Bot** — momentum-based decision engine with an LLM veto layer and live news intelligence
- ✍️ **LinkedIn Content Automation** — Node.js + Playwright posting pipeline with Claude-generated content and an Airtable review queue
---
 
## 📌 Why This Repo Exists
 
Most "AI transition" portfolios are either pure tutorials or pure theory. This one is different: it's built by someone who has spent 16+ years diagnosing why a TCP handshake doesn't complete across an asymmetric routing path — and is now applying that same rigor to understanding why a model's attention mechanism produces the output it does. The throughline is systems thinking, not a fresh start.
 
---
 
## 📬 Connect
 
Feedback, questions, or collaboration ideas are welcome — open an issue or connect on LinkedIn.
 
<div align="center">
*⭐ If this repo is useful to your own AI engineering journey, consider starring it.*
 
</div>
