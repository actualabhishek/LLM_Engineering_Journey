<div align="center">

# 🚀 LLM Engineering Journey

### From Network Engineer to AI Engineer

*A hands-on, code-first record of building my way into AI/ML — one notebook, one app, one shipped thing at a time.*

[![Jupyter Notebook](https://img.shields.io/badge/Jupyter-100%25-orange?logo=jupyter)](https://jupyter.org)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![HuggingFace](https://img.shields.io/badge/🤗-Transformers-yellow)](https://huggingface.co)
[![Colab](https://img.shields.io/badge/Google-Colab-F9AB00?logo=googlecolab)](https://colab.research.google.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 👋 About This Repo

I'm Abhishek — a Senior Network Engineer and Team Lead with 16+ years in enterprise infrastructure (F5 BIG-IP, Cisco Nexus, Palo Alto, Meraki, SD-WAN) for clients including Citi Group and British Petroleum. This repo is where I'm documenting my transition into AI/ML engineering — not a career reset, just two decades of systems thinking pointed at a new kind of infrastructure: large language models.

Nothing in here is a copied tutorial. Every notebook and app is something I actually ran, broke, and figured out — documented as I went, not cleaned up after the fact. I care more about understanding what's happening inside the model than about calling an API and moving on.

**How I work:** code-first, hands-on, run-the-cell-and-inspect-the-output. Every notebook carries Markdown notes on what I learned and why, so the repo doubles as a lab notebook, not just a code dump.

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
├── RAG/                          # RAG from scratch through applied chatbots —
│                                 # chunking, embeddings, retrieval, network SOP QA
│
├── LangGraph Agent/              # Self-correcting RAG pipeline (LangGraph + Chroma)
│                                 # for network ops SOPs, with retrieval grading
│
├── Network_KB_RAG_Claude/        # That LangGraph notebook, grown into a real app —
│                                 # Claude Opus + Haiku, groundedness evaluation,
│                                 # streaming Gradio UI
│
├── Autogen Agent/                # Multi-LLM-provider agent team (AutoGen) —
│                                 # OpenAI, Gemini, Claude collaborating in one chat
│
├── multi_agent_system/           # Researcher -> Analyst -> Writer pipeline
│                                 # (OpenAI Agents SDK), Tavily tool calling,
│                                 # Pydantic contracts, shared SQLiteSession
│
├── Store_Down_Automation/        # Four-agent + coordinator incident pipeline —
│                                 # browser automation, Pydantic hand-offs,
│                                 # supervised send-gate, Airtable-backed resume
│
├── ResumeRocket AI/              # End-to-end resume tailoring pipeline
│                                 # (gap analysis, rewrite, diff, cover letter)
│
├── CiscoConfigDiffAuditor/       # Block-aware Cisco IOS config diff tool with
│                                 # security risk flagging — built from 16 years
│                                 # of real config-review pain
│
├── Fine_Tuning/                  # QLoRA fine-tuning experiments
│
├── LinkedIn_Post_Automation/     # Telegram-driven LinkedIn content pipeline —
│                                 # Claude research + drafting, Gemini image gen,
│                                 # Airtable tracking, Playwright publish
│
├── .gitignore
└── README.md
```

---

## 🧠 What's Inside

### 1. LLM Fundamentals
From-first-principles notebooks: transformer internals, attention, tokenization, MLP/feed-forward blocks. The stuff I wanted to actually understand before building on top of it.

### 2. HuggingFace & Google Colab — Applied Projects
Hands-on notebooks, built and run on Colab's free-tier T4 GPU:

| Area | What It Covers |
|---|---|
| **Model Loading & Quantization** | Llama, Phi, Gemma, Qwen, DeepSeek compared with 4-bit NF4 quantization via BitsAndBytes |
| **NLP Pipelines** | Sentiment analysis, NER, question answering, summarization, translation, zero-shot classification |
| **Multimodal Generation** | Image generation (SDXL), text-to-speech (SpeechT5) |
| **Audio → Structured Text** | Whisper ASR + Llama 3.2 3B pipeline that turns meeting audio into structured Markdown minutes with owners on every action item |
| **Synthetic Data Generation** | Schema-constrained generation with sampled decoding and defensive JSON parsing |
| **Gradio Apps** | Dataset generator (Llama 3.1 8B), streaming AI tutor (OpenAI), multi-persona AI debate simulator (GPT-4o-mini, Claude, Llama via Ollama) |

### 3. RAG — Retrieval-Augmented Generation
Built up from first principles: chunking strategies, embeddings, retrieval, then applied to a real knowledge base and a network SOP assistant.

### 4. Agent Frameworks — LangGraph & AutoGen
Two different takes on multi-step, multi-agent systems: a self-correcting RAG pipeline that grades its own retrieval and retries on weak matches (LangGraph), and a multi-provider agent team where OpenAI, Gemini, and Claude each play a distinct role in one group chat (AutoGen).

### 5. Applied Tools
Six apps built to solve real problems, not just demo a model:
- **Network_KB_RAG_Claude** — the LangGraph notebook above, grown into a real app. Same self-correcting retrieval idea, but pushed further: `retrieve` (Chroma) → `grade_documents` (Haiku, relevance filter) → `generate` (Opus, answer synthesis) → `evaluate_answer` (Haiku, groundedness + relevance check) → `finalize`, with a retry loop if the answer doesn't hold up, served through a Gradio UI with real-time token streaming. Still pointed at my own TCS network SOPs as the test knowledge base.
- **multi_agent_system** — a Researcher → Analyst → Writer pipeline built with OpenAI's Agents SDK. A Tavily-backed Researcher gathers facts via tool calling (fact-only, no analysis), an Analyst extracts trends and risks from those facts, and a Writer turns that into a polished Markdown report — all chained through one `manager_run()` call, with Pydantic models (`ResearchOutput`, `AnalystOutput`) defining the handoff contract between agents and a shared `SQLiteSession` giving every agent visibility into the full run.
- **Store_Down_Automation** — a real NOC runbook automated end to end: four scoped subagents (incident watcher, directory lookup, email composer, logger) plus a deterministic Dispatcher coordinator, typed Pydantic hand-offs validated at every step, browser automation against systems with zero API access. The write-up covers three real debugging stories — discovering a directory site's hover contact-card was the actual source of truth for personal emails, tracing an "address-book search doesn't work" failure back to a wrong signed-in Microsoft account, and catching a UI that displays the literal text "No Match" in place of a name before it could get treated as real data.
- **ResumeRocket AI** — gap analysis, tailored rewrite, visual diff, and cover letter generation from a resume + job description.
- **CiscoConfigDiffAuditor** — a block-aware diff viewer for Cisco IOS configs, because a raw line diff on a reordered config tells you nothing. Flags security-relevant changes (ACLs, `shutdown`, `line vty`, `enable secret`) automatically.
- **LinkedIn_Post_Automation** — a Claude Code plugin that runs my LinkedIn content pipeline end to end: a Telegram message kicks off research, a draft in my own voice, an AI-generated image, and an Airtable-tracked approval step, then publishes to LinkedIn via Playwright once I approve.

Every notebook follows the same pattern: Markdown documentation and inline observations after every meaningful block, so it reads as a record of what I learned — not just what ran.

---

## 🛠️ Tech Stack

- **Frameworks:** 🤗 Transformers, PyTorch, BitsAndBytes, Accelerate, LangGraph, AutoGen, OpenAI Agents SDK, Claude Code (subagents + skills)
- **Models:** Llama (3.1 / 3.2), Phi, Gemma, Qwen, DeepSeek, Whisper, SDXL, SpeechT5, gpt-5-mini
- **Tools:** Google Colab (T4 GPU), Gradio, Hugging Face Hub, Chroma, Pydantic, Playwright/browser automation, Airtable
- **APIs:** Anthropic Claude, OpenAI, Gemini (via OpenRouter), Tavily
- **Techniques:** 4-bit NF4 quantization, chat-template prompting, streaming generation, structured-output prompting, RAG with self-grading retrieval, groundedness evaluation, schema-constrained synthetic data generation, typed multi-agent hand-off contracts

---

## 🗺️ Broader Portfolio Roadmap

This repo is one piece of a larger applied-AI portfolio I'm building alongside my day job. Related tracks, documented separately, for context:

- 🤖 **Network AI Agents** — Copilot Studio Roster Maker agent, Network Ops Daily Standup bot (Power Automate + Dataverse)
- 📈 **ForexAI Trader** — leading-indicator signal engine (RSI divergence, retest entries) with an LLM-based validator/veto layer
- 📊 **NIFTY 50 Options Bot** — momentum-based decision engine with an LLM veto layer and live news intelligence

---

## 📌 Why This Repo Exists

Most "AI transition" portfolios are either pure tutorials or pure theory. This one's grounded in the trenches: I've spent 16+ years figuring out why a TCP handshake won't complete across an asymmetric routing path, and now I'm applying that same rigor to figuring out why a model's attention mechanism produces the output it does. Same instinct, new domain. The throughline is systems thinking, not a fresh start.

---

## 📬 Connect

Feedback, questions, or collaboration ideas are welcome — open an issue or connect with me on LinkedIn.

<div align="center">

*⭐ If this repo is useful to your own AI engineering journey, consider starring it.*

</div>

Still learning, still building. Onward — one commit at a time.
