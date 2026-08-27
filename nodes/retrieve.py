"""
retrieve node — vector search against Chroma, returns top-k documents.

Uses `rewritten_query` if set (retry path), otherwise the original `question`.
"""

import logging
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

import config
from state import RAGState

log = logging.getLogger(__name__)

# Singleton vectorstore — loaded once per process
_vs: Chroma | None = None


def _get_vectorstore() -> Chroma:
    global _vs
    if _vs is None:
        embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
        _vs = Chroma(
            collection_name=config.COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=config.CHROMA_DIR,
        )
    return _vs


def retrieve(state: RAGState) -> dict:
    query = state.get("rewritten_query") or state["question"]
    retry = state.get("retry_count", 0)

    log.info("[retrieve] query=%r  retry=%d  top_k=%d", query, retry, config.TOP_K)

    vs = _get_vectorstore()
    docs = vs.similarity_search(query, k=config.TOP_K)

    log.info("[retrieve] returned %d documents", len(docs))
    return {"retrieved_docs": docs}
