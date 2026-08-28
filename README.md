# RAG Pipeline — LangGraph + Claude

16 years of networking, now speaking Python. This is a hands-on RAG (Retrieval-Augmented Generation) pipeline I built to actually understand how these systems work under the hood — not just call an API and hope for the best. It's built with LangGraph, ChromaDB, and Anthropic's Claude models, and it ingests PDF, DOCX, and plain text knowledge bases so you can ask questions and get grounded, cited answers back.

I'm using my own TCS network SOPs as the test knowledge base — felt right to point my first real AI project at the kind of documents I've lived in for 16 years.

## Architecture

```mermaid
flowchart TD
    A([User Question]) --> B[retrieve\nChroma similarity search]
    B --> C[grade_documents\nHaiku — relevance filter]
    C --> D[generate\nOpus — answer synthesis]
    D --> E[evaluate_answer\nHaiku — groundedness + relevance]
    E -- PASS --> F[finalize\nbuild final answer + sources]
    E -- "FAIL + retries left\n(rewritten query)" --> B
    E -- "FAIL + max retries" --> F
    F --> G([Final Answer + Sources])

    style B fill:#4A90D9,color:#fff
    style C fill:#F5A623,color:#fff
    style D fill:#7ED321,color:#fff
    style E fill:#F5A623,color:#fff
    style F fill:#9B59B6,color:#fff
```

I leaned on LangGraph specifically because it lets the pipeline retry itself — if an answer isn't grounded in the retrieved context, it rewrites the query and goes back for another pass instead of just shipping a shaky answer. That self-correction loop was the part I was most curious about, and it's still the part I find most satisfying to watch run in verbose mode.

## Project Structure

```
RAG_pipeline/
├── ingest.py          # Parse documents → Markdown → chunk → embed → Chroma
├── graph.py            # LangGraph StateGraph definition + conditional routing
├── state.py            # RAGState TypedDict (shared across all nodes)
├── config.py            # All configurable settings (reads from .env)
├── main.py              # CLI entrypoint (single query + interactive mode)
├── app.py               # Gradio web UI with real-time token streaming
├── nodes/
│   ├── retrieve.py    # Vector search node
│   ├── grade.py        # LLM relevance grading node (Haiku)
│   ├── generate.py     # Answer generation node (Opus)
│   ├── evaluate.py     # Answer quality evaluation node (Haiku)
│   └── finalize.py     # Package final answer + source citations
├── parsed/              # Auto-created: converted Markdown files
├── chroma_db/           # Auto-created: local Chroma vector store
├── .env.example         # Environment variable template
└── requirements.txt
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY
```

### 3. Ingest your knowledge base

```bash
# Single file
python ingest.py TCS_Network_KB_SOPs.docx

# Entire directory
python ingest.py ./docs/
```

This will:
- Parse the document to Markdown (saved in `parsed/`)
- Split into heading-aware chunks
- Embed with `all-MiniLM-L6-v2` (runs locally, no API key needed)
- Store in Chroma (`chroma_db/`)

### 4. Ask questions

CLI:

```bash
# Single question
python main.py "What is the escalation procedure for P1 network incidents?"

# Verbose (shows all node logs — good for watching the retry loop fire)
python main.py --verbose "How do I configure BGP failover?"

# Interactive mode
python main.py --interactive

# JSON output (for programmatic use)
python main.py --json "What are the SLA targets for network uptime?"
```

Or the web UI, if you'd rather see it stream live in the browser:

```bash
python app.py
```

Opens at `http://localhost:7860` with real-time token streaming, source citations, and the quality-check verdict shown alongside each answer.

## Pipeline Design Decisions

Documenting the "why" behind these choices, because that's the part that actually taught me something — anyone can copy a LangGraph tutorial, figuring out *why* one model goes where is where the learning happened.

### Model allocation

| Node | Model | Reason |
|------|-------|--------|
| `grade_documents` | `claude-haiku-4-5` | Binary YES/NO relevance — cheap and fast |
| `generate` | `claude-opus-4-8` | Answer quality is user-facing — strongest model |
| `evaluate_answer` | `claude-haiku-4-5` | Structured JSON verdict — Haiku handles this well |

No reason to send every step to the most expensive model. Route by how hard the task actually is.

### Chunking strategy

`MarkdownHeaderTextSplitter` splits first on `#`/`##`/`###`/`####` boundaries, so chunks never straddle section boundaries. `RecursiveCharacterTextSplitter` then sub-splits any oversized sections. Each chunk carries metadata: `source`, `section_heading`, `chunk_id`.

### Retry loop

`evaluate_answer` checks two properties:
1. **Groundedness** — every claim is supported by the retrieved context
2. **Relevance** — the answer addresses the question

On `FAIL`, it rewrites the query to guide the next retrieval round. The loop repeats up to `MAX_RETRIES` (default: 2) times before `finalize` delivers a best-effort answer with a warning. This is the piece that turns a plain retrieve-then-generate script into something closer to a real system.

### Parsing

| Format | Library | Why |
|--------|---------|-----|
| PDF | `pymupdf4llm` | Native Markdown output — headings, tables, lists preserved |
| DOCX | `python-docx` | Maps paragraph styles to `#`/`##`/`###` heading levels |
| TXT/MD | built-in | No conversion needed |

## Configuration

All settings live in `.env` (see `.env.example`). Key parameters:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required** |
| `GENERATOR_MODEL` | `claude-opus-4-8` | Model for answer generation |
| `GRADER_MODEL` | `claude-haiku-4-5` | Model for grading + evaluation |
| `TOP_K` | `5` | Number of chunks to retrieve |
| `MAX_RETRIES` | `2` | Max retry loops on evaluation FAIL |
| `CHUNK_SIZE` | `800` | Max characters per chunk |
| `CHUNK_OVERLAP` | `100` | Character overlap between chunks |

## About this project

I'm a Senior Network Engineer at TCS, 16+ years in — F5 BIG-IP, Cisco ISE, Nexus, Meraki, Cisco Voice, CEH — currently making a deliberate, hands-on transition into AI/ML engineering. This repo is part of that journey: real projects, real setbacks, built and documented as I go. More of the journey is at [github.com/actualabhishek/LLM_Engineering_Journey](https://github.com/actualabhishek/LLM_Engineering_Journey) and on LinkedIn.

Still learning, still building.
