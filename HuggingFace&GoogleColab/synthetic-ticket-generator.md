# 🧪 Synthetic Network Ticket Data Generator
### Schema-Constrained Synthetic Data Generation with Llama 3.2 3B (4-bit Quantized)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1somrXhp2YbfoZk51x1I7QpNdPig_6YXt#scrollTo=qoe_v986e1sq)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Transformers](https://img.shields.io/badge/🤗%20Transformers-4.57.6-yellow.svg)
![GPU](https://img.shields.io/badge/GPU-Colab%20T4-orange.svg)
![Quantization](https://img.shields.io/badge/Quantization-4--bit%20NF4-green.svg)

**Run it live:** https://colab.research.google.com/drive/1somrXhp2YbfoZk51x1I7QpNdPig_6YXt#scrollTo=qoe_v986e1sq

---

## 📌 Overview

This project generates **synthetic, schema-constrained support ticket data** for a network operations team using a locally-quantized instruction-tuned LLM — no external API, no paid data-generation service, and no manual data entry.

It takes the same core skill from the earlier audio-to-meeting-minutes pipeline (a quantized `meta-llama/Llama-3.2-3B-Instruct` model producing structured output from a system-prompt-defined schema) and repurposes it for a completely different job: **bulk synthetic dataset creation** instead of single-document summarization.

The result is a reusable CSV of realistic network ops tickets — spanning F5 BIG-IP, Cisco Nexus, Palo Alto, and Meraki MX devices — that can seed a triage classifier, populate a demo dashboard, or stress-test a ticketing workflow, all without touching real customer data.

---

## 🏗️ Architecture

```
 System Prompt (JSON Schema Definition)
      │
      ▼
┌─────────────────────────────────┐
│  Llama 3.2 3B Instruct            │   4-bit NF4 Quantized (BitsAndBytes)
│  loaded ONCE, reused across loop  │
└─────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────┐
│  Generation Loop (x50)            │   Sampled decoding
│  temperature=0.9, top_p=0.95      │   → diversity per ticket
└─────────────────────────────────┘
      │  raw text per iteration
      ▼
┌─────────────────────────────────┐
│  Defensive JSON Extraction         │   regex + json.loads
│  (skip malformed rows silently)   │
└─────────────────────────────────┘
      │
      ▼
  synthetic_network_tickets.csv
  (50 rows, structured, ready to use)
```

---

## ⚙️ Tech Stack

| Component | Technology |
|---|---|
| **Environment** | Google Colab (Free Tier — T4 GPU) |
| **LLM** | `meta-llama/Llama-3.2-3B-Instruct` |
| **Quantization** | BitsAndBytes 4-bit NF4, double quantization, `bfloat16` compute dtype |
| **Core Libraries** | `transformers==4.57.6`, `accelerate`, `bitsandbytes`, `torch` |
| **Sampling Strategy** | `do_sample=True`, `temperature=0.9`, `top_p=0.95` |
| **Parsing** | `re` (regex extraction) + `json.loads` with defensive error handling |
| **Output** | `pandas` DataFrame → CSV |
| **Auth** | HuggingFace Hub token via Colab secrets (`userdata`) |

---

## 🚀 What This Project Demonstrates

- **Schema-constrained generation** — the system prompt embeds an explicit JSON schema, steering a general-purpose instruct model to reliably act as a structured data generator rather than a conversational assistant.
- **Sampling-driven diversity** — `temperature=0.9` and `top_p=0.95` are the key levers that make each of the 50 generations meaningfully different instead of near-duplicate outputs, which is essential for synthetic data to be useful for downstream training/testing.
- **Efficient model reuse across a generation loop** — the model and tokenizer are loaded **once** outside the loop and reused for all 50 generations, avoiding the (very expensive) mistake of reloading a quantized model on every iteration.
- **Defensive parsing of LLM output** — a regex extraction step (`re.search(r"\{.*\}", text, re.DOTALL)`) pulls the JSON object out of any surrounding text, and malformed rows are caught and skipped via `json.JSONDecodeError` rather than crashing the whole batch.
- **Free-tier-friendly LLM inference at scale** — running 50 sequential generations from a 3B-parameter model on a single Colab T4 GPU, made possible by 4-bit NF4 quantization.
- **Practical enterprise automation use case** — this generator produces exactly the kind of labeled data needed to bootstrap a ticket-triage classifier or populate a network ops dashboard demo, directly extending the Network Ops Daily Standup bot and Roster Maker agent already in this portfolio.

---

## 📝 Pipeline Walkthrough

1. **Authenticate with HuggingFace** — log in using a Colab secret token to access the gated Llama 3.2 model.
2. **Load model and tokenizer once** — configure `BitsAndBytesConfig` for 4-bit NF4 quantization with double quantization and `bfloat16` compute, then load `meta-llama/Llama-3.2-3B-Instruct` with `device_map="auto"`. This happens a single time, before any generation.
3. **Define the schema** — a system message specifies the exact JSON fields expected (`ticket_id`, `device_type`, `issue_summary`, `severity`, `root_cause`, `resolution_steps`) and instructs the model to output *only* JSON, no prose or code fences.
4. **Loop 50 times** — for each iteration, build a fresh user prompt (referencing the ticket number and instructing variation from prior tickets), apply the chat template, and generate with sampling enabled for diversity.
5. **Extract and validate JSON** — for each generation, regex-extract the `{...}` block and attempt `json.loads`; malformed outputs are silently skipped rather than breaking the batch.
6. **Save to CSV** — all successfully parsed records are collected into a `pandas` DataFrame and written to `synthetic_network_tickets.csv`.

---

## 📄 Sample Output Row

```json
{
  "ticket_id": "TCK-0031",
  "device_type": "Palo Alto",
  "issue_summary": "VPN tunnel repeatedly drops during peak business hours.",
  "severity": "P2",
  "root_cause": "IKE Phase 2 rekey mismatch causing tunnel renegotiation failure.",
  "resolution_steps": [
    "Align rekey timers on both VPN peers",
    "Monitor tunnel stability for 24 hours post-fix"
  ]
}
```

---

## 🔮 Possible Extensions

- Add **Pydantic schema validation** so malformed rows are logged with the specific validation error instead of silently dropped.
- Fine-tune a lightweight classifier on the generated tickets to auto-predict `severity` or `device_type` from `issue_summary` alone.
- Parameterize the generator to accept a config file defining arbitrary schemas, turning this into a general-purpose synthetic data tool beyond network tickets.
- Add a **deduplication check** (e.g. embedding similarity) to catch near-identical tickets that slip through despite temperature sampling.
- Feed the generated CSV into a Gradio dashboard for a live "synthetic data preview" demo.

---

## 🔗 Notebook

**Google Colab:** https://colab.research.google.com/drive/1somrXhp2YbfoZk51x1I7QpNdPig_6YXt#scrollTo=qoe_v986e1sq

**Hardware used:** Google Colab Free Tier — NVIDIA T4 GPU

---

*Part of the [`llm-engineering-journey`](https://github.com/) portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.*
