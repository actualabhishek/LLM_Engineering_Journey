# RAG From Scratch — Chunking Strategies

Part of my [LLM Engineering Journey](https://github.com/actualabhishek/LLM_Engineering_Journey) — building a production-grade Retrieval-Augmented Generation (RAG) pipeline from first principles.

**▶️ Run it in Colab:** [Open Notebook](https://colab.research.google.com/drive/1xly2UnqnLyaLUzOaI0uHPZwvAvSI5kdH#scrollTo=7Ge-HpO8m4rl)

## What this covers

The single decision that affects RAG quality the most before you even touch embeddings or a vector store: **how you split documents into chunks**. This notebook implements and compares three chunking strategies from scratch, using sample network troubleshooting runbooks (BGP flapping, OSPF adjacency issues, F5 HA failover) as realistic test data drawn from my networking background.

| Strategy | Approach | Tradeoff |
|---|---|---|
| **Fixed-size** | Split every N characters with overlap | Simple and predictable, but can slice a step or sentence in half |
| **Recursive** | Try paragraph → sentence → word boundaries, in priority order, before falling back to a hard cut | Best default for most production RAG — respects document structure |
| **Semantic** | Embed sentences, cut wherever cosine similarity between consecutive sentences drops below a threshold | Chunks align with actual topic shifts, at the cost of extra embedding calls and less predictable chunk sizes |

## Tech stack

- `langchain-text-splitters` — `RecursiveCharacterTextSplitter`
- `sentence-transformers` (`all-MiniLM-L6-v2`) — embeddings for semantic chunking
- `numpy` — cosine similarity calculations
- Google Colab (CPU runtime — no GPU required for this stage)

## How it works

1. **Fixed-size chunking** — a from-scratch sliding-window function with configurable `chunk_size` and `overlap`
2. **Recursive chunking** — LangChain's splitter tries separators in priority order: paragraph breaks → line breaks → sentence endings → word boundaries → hard character cut, only falling through to a rougher cut when a piece is still too large
3. **Semantic chunking** — a from-scratch function that embeds each sentence, measures cosine similarity between consecutive sentences, and starts a new chunk wherever similarity drops below a threshold (default `0.5`)
4. **Comparison** — chunk count and average chunk size across all three methods, run against the same source document, so the tradeoffs are visible directly rather than theoretical

## Sample data

Three synthetic runbooks are generated inline in the notebook (no external files needed to run it):
- `bgp_flap_runbook.txt`
- `ospf_adjacency_runbook.txt`
- `f5_ha_failover_runbook.txt`

## Next steps in this project

This is Part 2 of the RAG build (Part 1 covers embeddings and vector similarity fundamentals). Upcoming parts:
- Embeddings + FAISS vector store (local, free)
- Retrieval strategies: similarity search, MMR, hybrid search, re-ranking
- Generation with both an open-source model (quantized Llama 3.1 8B) and a closed-source API (Claude/OpenAI)
- Evaluation with RAGAS (faithfulness, answer relevance, context precision/recall)
- **Capstone:** a fully functional RAG application with a Gradio UI, swappable open/closed-source generator, and a clean modular repo structure

## About this journey

I'm a Senior Network Engineer (16+ years, F5/Cisco/Palo Alto/SD-WAN) transitioning into AI/ML engineering.


- GitHub: [actualabhishek/LLM_Engineering_Journey](https://github.com/actualabhishek/LLM_Engineering_Journey)
- LinkedIn: [abhishek-suman-8919b338](https://linkedin.com/in/abhishek-suman-8919b338)
