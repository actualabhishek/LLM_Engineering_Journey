<div align="center">

# 🚀 LLM Engineering Journey

### GenAI/LLM projects: shipped fast with Claude Code, fundamentals built by hand

*A hands-on, code-first record of building GenAI/LLM systems, one notebook, one app, one shipped thing at a time.*

[![Jupyter Notebook](https://img.shields.io/badge/Jupyter-100%25-orange?logo=jupyter)](https://jupyter.org)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![HuggingFace](https://img.shields.io/badge/🤗-Transformers-yellow)](https://huggingface.co)
[![Colab](https://img.shields.io/badge/Google-Colab-F9AB00?logo=googlecolab)](https://colab.research.google.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 👋 About This Repo

I'm Abhishek. I build GenAI and LLM systems in two ways, on purpose. Most of the apps in this repo were built with Claude Code, which is how I go from idea to something running quickly. The fundamentals work (QLoRA fine-tuning, a self-correcting LangGraph retrieval agent, multi-agent systems in AutoGen, CrewAI and the OpenAI Agents SDK) I built independently, without Claude Code, to understand what is underneath. I am a Senior Network Engineer at TCS, and 17 years of networking is why so many of these projects point at real operations problems.

Nothing in here is a copied tutorial. Every notebook and app is something I actually ran, broke, and figured out — documented as I went, not cleaned up after the fact. I care more about understanding what's happening inside the model than about calling an API and moving on.

**How I work:** code-first, hands-on, run-the-cell-and-inspect-the-output. Every notebook carries Markdown notes on what I learned and why, so the repo doubles as a lab notebook, not just a code dump.

### How each project was built

| Built with Claude Code | Built independently (no Claude Code) |
|---|---|
| Network_KB_RAG_Claude, Store_Down_Automation, NetOps_Flow_Kanban, AI_Forex_Bot, Hotel_Experience_Assistant, LinkedIn_Post_Automation (postflow), Portfolio_Website (Digital Twin), Router_Reachability_Monitor | Fine_Tuning (QLoRA), LangGraph Agent (self-correcting retrieval), Autogen Agent, multi_agent_system, CiscoConfigDiffAuditor |

llm_fundamentals, HuggingFace&GoogleColab, RAG (from scratch) and ResumeRocket AI are learning notebooks and apps; build method is not tagged here.

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
├── Router_Reachability_Monitor/   # Edge-router reachability monitor: probes, UP/DOWN state
│                                 # machine, multi-channel alerts, live dashboard (no LLM)
│
├── Store_Down_Automation/        # Four-agent + coordinator incident pipeline —
│                                 # browser automation, Pydantic hand-offs,
│                                 # supervised send-gate, Airtable-backed resume
│
├── AI_Forex_Bot/                 # Autonomous MT5 forex trading system —
│                                 # deterministic technical analysis + selective
│                                 # LLM reasoning, TradingView webhook signals,
│                                 # multi-layer risk management, Streamlit dashboard
│
├── ResumeRocket AI/              # End-to-end resume tailoring pipeline
│                                 # (gap analysis, rewrite, diff, cover letter)
│
├── CiscoConfigDiffAuditor/       # Block-aware Cisco IOS config diff tool with
│                                 # security risk flagging — built from real
│                                 # config-review pain
│
├── Fine_Tuning/                  # QLoRA fine-tuning experiments
│
├── LinkedIn_Post_Automation/     # Telegram-driven LinkedIn content pipeline —
│                                 # Claude research + drafting, Gemini image gen,
│                                 # Airtable tracking, Playwright publish
│
├── Portfolio_Website/            # Next.js portfolio site with an AI "Digital
│                                 # Twin" chat agent grounded in my own resume,
│                                 # served through a server-side OpenRouter route
│
├── NetOps_Flow_Kanban/           # Kanban board for network ops with an AI
│                                 # sidebar that creates, edits and moves cards —
│                                 # FastAPI serving a Next.js static export,
│                                 # SQLite, one Docker container
│
├── Hotel_Experience_Assistant/   # Bilingual (EN/HI) hotel voice concierge —
│                                 # no text input, guest just talks. LLM agent
│                                 # with propose-then-confirm tools, a Modal GPU
│                                 # worker for STT/TTS, one Docker container
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
Ten apps built to solve real problems, not just demo a model:
- **Network_KB_RAG_Claude** — the LangGraph notebook above, grown into a real app. Same self-correcting retrieval idea, but pushed further: `retrieve` (Chroma) → `grade_documents` (Haiku, relevance filter) → `generate` (Opus, answer synthesis) → `evaluate_answer` (Haiku, groundedness + relevance check) → `finalize`, with a retry loop if the answer doesn't hold up, served through a Gradio UI with real-time token streaming. Still pointed at my own TCS network SOPs as the test knowledge base. *Built with Claude Code.*
- **multi_agent_system** — a Researcher → Analyst → Writer pipeline built with OpenAI's Agents SDK. A Tavily-backed Researcher gathers facts via tool calling (fact-only, no analysis), an Analyst extracts trends and risks from those facts, and a Writer turns that into a polished Markdown report — all chained through one `manager_run()` call, with Pydantic models (`ResearchOutput`, `AnalystOutput`) defining the handoff contract between agents and a shared `SQLiteSession` giving every agent visibility into the full run. *Built independently.*
- **Store_Down_Automation** — a real NOC runbook automated end to end: four scoped subagents (incident watcher, directory lookup, email composer, logger) plus a deterministic Dispatcher coordinator, typed Pydantic hand-offs validated at every step, browser automation against systems with zero API access. A safe dev-mode lane (sandboxed ticketing instance, draft-only notifications to a personal inbox) now lets the full pipeline — finalize step included — run end to end with zero real-world risk. The write-up covers four real debugging stories, the latest one only surfaced by that first end-to-end dev-mode run: discovering a directory site's hover contact-card was the actual source of truth for personal emails, tracing an "address-book search doesn't work" failure back to a wrong signed-in Microsoft account, catching a UI that displays the literal text "No Match" in place of a name before it could get treated as real data, and finding a store-code placeholder in the email template that had never actually been wired up. *Built with Claude Code.*
- **AI_Forex_Bot** — an autonomous forex trading system for MT5: deterministic technical analysis (multi-timeframe alignment, an 8-factor 0-100 confidence score) feeds a hybrid decision engine that only calls an LLM when the signal is genuinely ambiguous (score 55-75), with a hard cap on how much the LLM can move the needle. TradingView webhooks (HMAC-validated) supply signals, a multi-layer risk engine gates every trade, and a Streamlit dashboard shows it live. The README documents a real debugging story: a 270-day gold (XAUUSD) backtest that looked fine until I fixed a pip-value bug specific to metals — the honest result was a 127% max drawdown, traced back to the broker's minimum lot size silently overriding the risk engine's 1%-per-trade target. Gold stays out of the live pair list until that's actually solved. *Built with Claude Code.*
- **ResumeRocket AI** — gap analysis, tailored rewrite, visual diff, and cover letter generation from a resume + job description.
- **CiscoConfigDiffAuditor** — a block-aware diff viewer for Cisco IOS configs, because a raw line diff on a reordered config tells you nothing. Flags security-relevant changes (ACLs, `shutdown`, `line vty`, `enable secret`) automatically. *Built independently.*
- **LinkedIn_Post_Automation** — a Claude Code plugin that runs my LinkedIn content pipeline end to end: a Telegram message kicks off research, a draft in my own voice, an AI-generated image, and an Airtable-tracked approval step, then publishes to LinkedIn via Playwright once I approve. *Built with Claude Code.*
- **NetOps_Flow_Kanban** — a Kanban board built for how network teams actually track work: cards are change requests, incidents and tasks, with ticket ids, P1/P2 priorities and CAB approval windows. The AI sidebar doesn't just talk about the board, it changes it — create a card, edit one, move it between columns, rename a column, or several in a single instruction. Board state goes to the model with every message so it can act on cards by ticket id, and what comes back is a small JSON list of actions the backend validates and applies against SQLite. No agent framework; a typed contract and the same ordering and uniqueness rules the UI writes through. It ships as one container: FastAPI serves the API and a Next.js static export from a single origin, so there's no Node process at runtime. Two things worth writing down. A full code review caught that drag-and-drop reordering was never actually persisting — only the dragged card's position was being written, so positions collided and `ORDER BY position` quietly handed back the old order on reload; it looked fine until you refreshed. And a 20-second delay on every AI call that I spent a while blaming on the model turned out to be dead IPv6 on my own machine: `httpx` was waiting out the full connect timeout before falling back to IPv4, and a no-inference request to the same host took exactly as long. The container never had the problem. Good reminder to measure the thing you're actually accusing. *Built with Claude Code.*
- **Hotel_Experience_Assistant** — a bilingual (English/Hindi) voice concierge for a hotel (Velvet Vista Hotel, if you're asking — now with an actual brand: a velvet-and-gold theme, a VV monogram logo I had to redraw once because it read as a "W," and an assistant with a name, Divya), no text input anywhere: a guest taps Start, talks, and the assistant talks back. Six phases, each proved with real commands and real output before moving to the next: SQLAlchemy data plus booking/loyalty/check-in services, an LLM tool-calling agent (OpenRouter) where every data-changing action is proposed, then only actually carried out after the guest confirms — the model has to call the same tool a second time, not just say "done," a distinction that mattered more than I expected once I watched it fail. Speech runs on a serverless GPU worker on Modal (faster-whisper for STT, Kokoro and Indic Parler-TTS for the reply), reached over a WebSocket from a FastAPI app that otherwise runs CPU-only in one Docker container, with browser-side Silero VAD handling barge-in. Proven end to end with a Playwright test that feeds Chromium a fake microphone and completes a real booking by voice against the running container — real STT, real LLM, real TTS, nothing mocked. A few things worth writing down. A Hindi-speaking guest naturally gives their last name in Devanagari ("वर्मा"), but names are stored in Latin script, so identity lookups silently failed until the system prompt was told to transliterate before calling a tool. A security review on the very last phase caught that an unset session secret would let anyone forge an admin login and skip the password check entirely — the same fail-closed guard I'd already written for the password itself, just missing on the key that signs the cookie. After shipping, real usage surfaced something no synthetic test audio ever would: Hindi speech sometimes got transcribed as unrelated English words, traced to Whisper's language auto-detection scoring across all ~99 languages it knows instead of just the two this app needs — now re-scored against just English and Hindi. And the most useful bug of all showed up while reviewing my own screenshots after the redesign: the assistant's booking confirmation had visibly leaked model reasoning into what the guest would hear. I didn't patch around it — I A/B tested with and without OpenRouter's reasoning-exclude flag, found the corruption happened either way, and traced it to OpenRouter load-balancing that model across several third-party backends, at least one of which was unreliable. Rather than keep layering retry logic on a model I couldn't trust, I switched to a single first-party-routed model instead, and a 0/8 stress test replacing a 2/6 failure rate is the kind of before/after I actually want on a portfolio piece. *Built with Claude Code.*
- **Router_Reachability_Monitor** — external reachability monitoring for two internet edge routers. ICMP and TCP probes with a canary check so a local outage is not mistaken for a router outage, an UP/DOWN state machine with debounce, alerts over Telegram, voice call, WhatsApp and ntfy, and a live dashboard, shipped as one Docker image behind Tailscale. Monitoring automation, no LLM. *Built with Claude Code.*

### 6. Fine-Tuning
QLoRA experiments on TinyLlama and Gemma — 4-bit quantized base model, LoRA adapters on the attention projections, trained with `trl`'s `SFTTrainer`, then compared side by side against the frozen base model using `peft`'s `disable_adapter()` context manager (no second model load needed) to see exactly what the fine-tune changed.

### 7. Portfolio Website & Digital Twin
Where the journey gets a front door. A Next.js (App Router, TypeScript, Tailwind) portfolio site that has to do two jobs at once: read as a credible engineering portfolio, and let visitors actually talk to an AI version of me. The Digital Twin is a server-side route that calls OpenRouter, grounded in a condensed context file built from my real resume — not the raw PDF, and not a general-purpose chatbot. It answers in first person, stays inside the facts it's given, and is built to resist prompt-injection attempts from visitors poking at it, which doubles as a live demo of taking that seriously rather than just claiming to. Deployed on Vercel.

Every notebook follows the same pattern: Markdown documentation and inline observations after every meaningful block, so it reads as a record of what I learned — not just what ran.

---

## 🛠️ Tech Stack

- **Frameworks:** 🤗 Transformers, PyTorch, BitsAndBytes, Accelerate, LangGraph, AutoGen, OpenAI Agents SDK, Claude Code (subagents + skills)
- **Models:** Llama (3.1 / 3.2), Phi, Gemma, Qwen, DeepSeek, Whisper, faster-whisper, Kokoro, Indic Parler-TTS, SDXL, SpeechT5, gpt-5-mini
- **Tools:** Google Colab (T4 GPU), Modal (serverless GPU), Gradio, Hugging Face Hub, Chroma, Pydantic, Playwright/browser automation, Airtable, Docker
- **Web:** Next.js (App Router), TypeScript, Tailwind CSS, Vercel, FastAPI, SQLite, WebSockets
- **APIs:** Anthropic Claude, OpenAI, Gemini, OpenRouter, Tavily
- **Techniques:** 4-bit NF4 quantization, chat-template prompting, streaming generation, structured-output prompting, RAG with self-grading retrieval, groundedness evaluation, schema-constrained synthetic data generation, typed multi-agent hand-off contracts

---

## 🗺️ Broader Portfolio Roadmap

This repo is one piece of a larger applied-AI portfolio I'm building alongside my day job. Related tracks, documented separately, for context:

- 🤖 **Network AI Agents** — Copilot Studio Roster Maker agent, Network Ops Daily Standup bot (Power Automate + Dataverse)
- 📊 **NIFTY 50 Options Bot** — momentum-based decision engine with an LLM veto layer and live news intelligence

---

## 📌 Why This Repo Exists

Most AI portfolios are either pure tutorials or pure theory. This one is grounded in real operations work. My day job is figuring out why a call will not connect or a session will not come up, and I point the same habit, test before you trust, at LLM systems. Claude Code gets me to a working tool fast, and the fundamentals work is how I make sure I understand what it built. The throughline is systems thinking.

---

## 📬 Connect

Feedback, questions, or collaboration ideas are welcome — open an issue or connect with me on LinkedIn.

<div align="center">

*⭐ If this repo is useful to your own AI engineering journey, consider starring it.*

</div>

---

Part of the `llm-engineering-journey` portfolio: GenAI/LLM projects built with Claude Code, plus fundamentals built independently. Background: 17 years in networking.

Still learning. Still building.
