# RAG From Scratch — Chunking → Embedding → Retrieval → Gradio Chat

Part of my [LLM Engineering Journey](https://github.com/actualabhishek/LLM_Engineering_Journey) — building a production-grade Retrieval-Augmented Generation (RAG) pipeline from first principles, using network troubleshooting runbooks (BGP, OSPF, F5 HA) as the knowledge base.

**▶️ Run it in Colab:** [Open Notebook](https://colab.research.google.com/drive/1-T70dxuaJ7SvEC9i8S1eF8JBroLg5NM6#scrollTo=8IcS7jq7QANY)

## What this does

Ask a question in plain English — e.g. *"why does OSPF adjacency get stuck in 2-way state?"* — and get back the exact runbook passages relevant to it, retrieved by meaning rather than keyword matching. No LLM writes the answer (yet); this stage proves that chunking, embedding, and retrieval are working correctly end to end, with a real chat UI to query it interactively.

## Pipeline

| Stage | What happens | Key tool |
|---|---|---|
| **1. Chunk** | Split each runbook into smaller pieces along natural boundaries (paragraph → sentence → word), so a "Step N" instruction never gets cut in half | `RecursiveCharacterTextSplitter` |
| **2. Embed** | Convert every chunk into a 384-number vector that captures its meaning — chunks about similar topics land close together in vector space, even without shared words | `sentence-transformers` (`all-MiniLM-L6-v2`) |
| **3. Index** | Store all vectors in a structure built for fast "find the closest match" lookups | `FAISS` (`IndexFlatL2`) |
| **4. Retrieve** | Embed the user's question the same way, then return the top-k closest chunks by similarity | Custom `search()` function |
| **5. Chat UI** | A browser-based chat window to ask questions and see retrieved results live | `Gradio` (`ChatInterface`) |

## Tech stack

- `langchain-text-splitters` — recursive chunking
- `sentence-transformers` (`all-MiniLM-L6-v2`) — free, open-source embeddings
- `faiss-cpu` — local vector store, no server required
- `gradio` — chat interface, shareable via a public URL (`share=True`) directly from Colab

## How to run

1. Open the notebook in Colab (link above) or run `rag_pipeline_gradio.py` in PyCharm scientific mode (`#%%` cells)
2. Run all cells top to bottom — each section depends on files saved by the one before it (`chunks.json`, `runbooks.faiss`, `chunk_embeddings.npy`)
3. The last cell launches Gradio and prints a public URL like `https://xxxxx.gradio.live` — open it and start asking questions

## Sample data

Three synthetic runbooks generated inline (no external files needed):
- `bgp_flap_runbook.txt` — BGP session flapping
- `ospf_adjacency_runbook.txt` — OSPF adjacency stuck in 2-way/init
- `f5_ha_failover_runbook.txt` — F5 BIG-IP HA failover not triggering

Swap in your own `.txt` runbooks by dropping them into the `runbooks/` folder — no code changes needed.

## Current limitation (by design, for now)

This stage is **retrieval-only** — it returns the raw matching chunks, not a generated natural-language answer. That's intentional: it isolates and proves the retrieval half of RAG before adding an LLM on top.

## Next steps

- **Generation**: feed retrieved chunks into an LLM (open-source via Ollama/quantized Llama, or closed-source via Claude/OpenAI API) so it synthesizes an actual answer instead of returning raw text
- **Evaluation**: RAGAS-based scoring for faithfulness, answer relevance, and context precision/recall
- **Re-ranking**: add a cross-encoder step to catch cases where similarity search alone pulls back topically-close-but-factually-wrong chunks
- **Capstone**: swappable open/closed-source generator, modular repo structure, real runbook/ticket data

## About this journey

I'm a Senior Network Engineer (16+ years, F5/Cisco/Palo Alto/SD-WAN) transitioning into AI/ML engineering. This project is part of my public build-in-the-open portfolio.

- GitHub: [actualabhishek/LLM_Engineering_Journey](https://github.com/actualabhishek/LLM_Engineering_Journey)
- LinkedIn: [abhishek-suman-8919b338](https://linkedin.com/in/abhishek-suman-8919b338)

---

Part of the `llm-engineering-journey` portfolio — documenting a hands-on transition from 16+ years of enterprise network engineering into AI/ML engineering.
