"""
finalize node — packages the generation + source citations into the final output.

Also attaches a warning banner when the answer is delivered after max retries
without a PASS evaluation (best-effort answer).
"""

import logging
from state import RAGState

log = logging.getLogger(__name__)


def finalize(state: RAGState) -> dict:
    generation = state.get("generation", "No answer was generated.")
    docs = state.get("graded_docs") or state.get("retrieved_docs", [])
    evaluation = state.get("evaluation")
    retry_count = state.get("retry_count", 0)

    # Deduplicate sources
    seen: set[str] = set()
    sources: list[dict] = []
    for doc in docs:
        cid = doc.metadata.get("chunk_id", "")
        if cid not in seen:
            seen.add(cid)
            sources.append(
                {
                    "source": doc.metadata.get("source", "unknown"),
                    "section_heading": doc.metadata.get("section_heading", ""),
                    "chunk_id": cid,
                }
            )

    final_answer = generation
    if evaluation and evaluation.get("verdict") == "FAIL":
        warning = (
            f"\n\n⚠️  Note: This answer did not pass quality evaluation after "
            f"{retry_count} retry attempt(s). "
            f"Reason: {evaluation.get('reason', '')}. "
            "Please verify the information independently."
        )
        final_answer += warning

    log.info(
        "[finalize] answer ready  sources=%d  retries=%d  verdict=%s",
        len(sources),
        retry_count,
        evaluation.get("verdict", "N/A") if evaluation else "N/A",
    )

    return {"final_answer": final_answer, "sources": sources}
