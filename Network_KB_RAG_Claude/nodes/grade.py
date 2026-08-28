"""
grade_documents node — filters retrieved chunks to only those relevant to the question.

Uses claude-haiku-4-5 (fast, cheap) — one API call per chunk, binary YES/NO verdict.
Each call is independent so we could parallelize, but serial is simpler and cheaper.
"""

import logging
import anthropic
from langchain_core.documents import Document

import config
from state import RAGState

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


_GRADE_PROMPT = """\
You are a relevance grader for a RAG pipeline.

Question:
{question}

Retrieved chunk:
\"\"\"
{chunk}
\"\"\"

Task: Decide whether this chunk contains information that is USEFUL for answering the question.
Respond with exactly one word on the first line: YES or NO.
Then write one sentence explaining your decision.
"""


def _grade_single(question: str, doc: Document) -> bool:
    prompt = _GRADE_PROMPT.format(question=question, chunk=doc.page_content[:2000])
    response = _get_client().messages.create(
        model=config.GRADER_MODEL,
        max_tokens=64,
        messages=[{"role": "user", "content": prompt}],
    )
    verdict_line = response.content[0].text.strip().splitlines()[0].upper()
    return verdict_line.startswith("YES")


def grade_documents(state: RAGState) -> dict:
    question = state.get("rewritten_query") or state["question"]
    docs = state["retrieved_docs"]

    log.info("[grade_documents] grading %d chunks for question=%r", len(docs), question)

    graded: list[Document] = []
    for i, doc in enumerate(docs):
        relevant = _grade_single(question, doc)
        status = "KEEP" if relevant else "DROP"
        log.info(
            "  chunk %d [%s] source=%s  heading=%s",
            i,
            status,
            doc.metadata.get("source", "?"),
            doc.metadata.get("section_heading", "?"),
        )
        if relevant:
            graded.append(doc)

    log.info("[grade_documents] %d / %d chunks passed", len(graded), len(docs))
    return {"graded_docs": graded}
