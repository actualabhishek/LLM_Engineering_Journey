# NetSOP-RAG — LangGraph RAG Pipeline for Network SOPs

A self-correcting Retrieval-Augmented Generation (RAG) assistant for network operations Standard Operating Procedures (F5 BIG-IP, Cisco Nexus, VLAN/trunk configuration, BGP troubleshooting), built with [LangGraph](https://langchain-ai.github.io/langgraph/), OpenAI, and Chroma, and served through a Gradio chat UI.

## What it does

The notebook ([`RAG_Pipeline_LangGraph.ipynb`](./RAG_Pipeline_LangGraph.ipynb)) turns a single SOP document into a queryable assistant that:

1. Converts the source `.docx` into Markdown (preserving tables) so commands stay linked to their expected results.
2. Chunks and embeds the document into a local Chroma vector store.
3. Answers questions strictly from retrieved SOP content — no guessing, exact command reproduction, section citations.
4. **Grades its own retrieval quality** before answering, and if the retrieved context is insufficient, automatically rewrites the question and retries (up to a retry cap) rather than answering from a weak match.
5. Exposes the whole pipeline as a Gradio chat interface.

## Architecture

The pipeline is a LangGraph `StateGraph` with a self-correcting retrieval loop:

```
START → retrieve → grade_document ──sufficient──→ generate → END
                         │
                    insufficient
                         │
                         ▼
                  transform_query → retrieve (retry, up to MAX_RETRIES)
```

**Shared state (`RAGState`):** `question`, `context`, `answer`, `grade`, `retry_count` — passed between every node; each node only updates the fields it's responsible for.

**Nodes:**

| Node | Responsibility |
|---|---|
| `retrieve` | Vector-search the SOP knowledge base for chunks relevant to the current question. |
| `grade_document` | LLM call (structured output) that judges whether the retrieved context is actually enough to answer — the self-correction gate. |
| `transform_query` | Rewrites a vague question into a sharper, retrieval-friendly one when grading fails, and increments the retry counter. |
| `generate` | Synthesizes the final answer strictly from the retrieved context, following an operational system prompt (cite sections, preserve command/step order, surface rollback steps for failures). |

## Project files

| File | Purpose |
|---|---|
| `RAG_Pipeline_LangGraph.ipynb` | Main notebook — builds and runs the pipeline end-to-end. |
| `docx_markdown_loader.py` | Custom loader that converts a `.docx` into Markdown, rendering tables as Markdown pipe-tables so command/result pairs aren't split apart by chunking. |
| `TCS_Network_KB_SOPs.docx` | Source knowledge base document (SOPs for F5, Nexus, VLAN/trunk, BGP). |
| `vector_db_langgraph_v1/` | Persisted Chroma vector store (regenerated each time the notebook's embedding cell is run). |

## Setup

1. Install dependencies:
   ```bash
   pip install langgraph langchain-core langchain-openai langchain-chroma langchain-text-splitters python-docx python-dotenv pydantic gradio openai
   ```
2. Create a `.env` file in this folder with your OpenAI key:
   ```
   OPENAI_API_KEY=sk-...
   ```
3. Run the notebook top to bottom. This will:
   - Load and chunk `TCS_Network_KB_SOPs.docx`
   - Build (or rebuild) the Chroma vector store in `vector_db_langgraph_v1/`
   - Compile the LangGraph pipeline
   - Launch a Gradio chat UI (with a temporary public share link)

## Configuration knobs

- `MODEL` — the OpenAI chat model used for grading, query rewriting, and generation (default `gpt-4o-mini`).
- `chunk_size` / `chunk_overlap` in the text splitter — controls how the SOP document is broken into retrievable pieces (default 1200 / 200 characters).
- `search_kwargs={"k": 4}` — number of chunks retrieved per query.
- `MAX_RETRIES` — how many times the pipeline will rewrite-and-retry retrieval before answering anyway (default 2).

## Notes

- Answers are constrained to only use retrieved SOP content; if the knowledge base has no good match even after retries, the assistant says so rather than guessing.
- Swap in a different source document by changing `FILEPATH` and re-running the loading/chunking/embedding cells.

---

This project is part of my [LLM Engineering journey](../).
