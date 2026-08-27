"""
generate node — synthesizes an answer from graded docs using claude-opus-4-8.

If no graded docs survived (all dropped), falls back to retrieved_docs so the
pipeline always has something to work with rather than producing an empty answer.
"""

import logging
import anthropic

import config
from state import RAGState

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


_SYSTEM_PROMPT = """\
You are a knowledgeable assistant answering questions from an internal knowledge base.

Rules:
1. Answer ONLY using information present in the provided context chunks.
2. If the context does not contain enough information to answer, say so explicitly — do not guess.
3. Cite your sources inline as [Source: <filename>, Section: <heading>].
4. Be concise and structured. Use bullet points or numbered lists where appropriate.
"""

_USER_TEMPLATE = """\
Question: {question}

Context chunks:
{context}

Answer:"""


def _format_context(docs) -> str:
    parts = []
    for i, doc in enumerate(docs, 1):
        src = doc.metadata.get("source", "unknown")
        heading = doc.metadata.get("section_heading", "—")
        parts.append(f"[{i}] Source: {src} | Section: {heading}\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def generate(state: RAGState) -> dict:
    question = state.get("rewritten_query") or state["question"]
    docs = state.get("graded_docs") or state.get("retrieved_docs", [])

    if not docs:
        log.warning("[generate] No documents available — returning empty-context response")
        return {"generation": "I could not find relevant information in the knowledge base to answer this question."}

    context = _format_context(docs)
    user_msg = _USER_TEMPLATE.format(question=question, context=context)

    log.info("[generate] generating answer from %d docs with %s", len(docs), config.GENERATOR_MODEL)

    response = _get_client().messages.create(
        model=config.GENERATOR_MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    # Extract text blocks (skip thinking blocks)
    answer = "\n".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    log.info("[generate] answer length=%d chars", len(answer))
    return {"generation": answer}
