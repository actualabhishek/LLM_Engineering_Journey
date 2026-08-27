import os
from dotenv import load_dotenv

load_dotenv()

# ── Anthropic models ──────────────────────────────────────────────────────────
GRADER_MODEL = os.getenv("GRADER_MODEL", "claude-haiku-4-5")
GENERATOR_MODEL = os.getenv("GENERATOR_MODEL", "claude-opus-4-8")

# ── Retrieval ─────────────────────────────────────────────────────────────────
TOP_K = int(os.getenv("TOP_K", "5"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))  # max re-retrieve loops

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

# ── Paths ─────────────────────────────────────────────────────────────────────
PARSED_DIR = os.getenv("PARSED_DIR", "parsed")
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "rag_kb")

# ── Embeddings ────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# ── Anthropic API ─────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# Key is validated lazily — only nodes that call Claude will check it,
# so `ingest.py` (which never calls Claude) can run without the key.
