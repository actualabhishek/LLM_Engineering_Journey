"""
generate node — synthesizes an answer from graded docs using claude-opus-4-8.

Supports optional token streaming via a module-level sink callable.
Set it with set_token_sink() before invoking the pipeline (used by app.py).
When no sink is set, falls back to a standard blocking API call (CLI use).
"""

import logging
from typing import Callable, Optional
import anthropic

import config
from state import RAGState

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None

# Set by app.py before each pipeline invocation; None in CLI mode.
_token_sink: Optional[Callable[[str], None]] = None


def set_token_sink(fn: Optional[Callable[[str], None]]) -> None:
    global _token_sink
    _token_sink = fn


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """\
You are a knowledgeable assistant answering questions from an internal knowledge base.

Rules:
1. Answer ONLY using information present in the provided context chunks.
2. If the context does not contain enough information to answer, say so explicitly — do not guess.
3. Cite your sources inline as [Source: <filename>, Section: <heading>].
4. Be concise and structured. Use bullet points or numbered lists where appropriate.
"""

USER_TEMPLATE = """\
Question: {question}

Context chunks:
{context}

Answer:"""


def format_context(docs) -> str:
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
        empty = "I could not find relevant information in the knowledge base to answer this question."
        if _token_sink:
            _token_sink(empty)
        return {"generation": empty}

    context = format_context(docs)
    user_msg = USER_TEMPLATE.format(question=question, context=context)

    log.info("[generate] generating answer from %d docs with %s", len(docs), config.GENERATOR_MODEL)

    common_kwargs = dict(
        model=config.GENERATOR_MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    if _token_sink:
        # Streaming path — feed each text token to the sink as it arrives.
        # text_stream skips thinking blocks automatically.
        parts: list[str] = []
        with _get_client().messages.stream(**common_kwargs) as stream:
            for token in stream.text_stream:
                parts.append(token)
                _token_sink(token)
        answer = "".join(parts).strip()
    else:
        # Blocking path (CLI).
        response = _get_client().messages.create(**common_kwargs)
        answer = "\n".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

    log.info("[generate] answer length=%d chars", len(answer))
    return {"generation": answer}
