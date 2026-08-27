"""
graph.py — LangGraph StateGraph definition for the RAG pipeline.

Flow:
  retrieve → grade_documents → generate → evaluate_answer
                                               ↓
                                     [PASS] → finalize
                                     [FAIL, retries left] → retrieve (rewritten query)
                                     [FAIL, max retries hit] → finalize (with warning)

Retry counter is incremented inside the conditional router — not in any node —
so nodes stay pure (they only read/write their own slice of state).
"""

import logging
from langgraph.graph import StateGraph, END

from state import RAGState
import config

from nodes.retrieve import retrieve
from nodes.grade import grade_documents
from nodes.generate import generate
from nodes.evaluate import evaluate_answer
from nodes.finalize import finalize

log = logging.getLogger(__name__)


# ── Conditional router ────────────────────────────────────────────────────────

def _route_after_evaluation(state: RAGState) -> str:
    """
    Decides what happens after evaluate_answer:
      - PASS                     → finalize
      - FAIL + retries remaining → retrieve  (with incremented retry_count)
      - FAIL + max retries hit   → finalize  (best-effort, with warning)
    """
    evaluation = state.get("evaluation")
    retry_count = state.get("retry_count", 0)

    if evaluation is None or evaluation.get("verdict") == "PASS":
        log.info("[router] verdict=PASS → finalize")
        return "finalize"

    if retry_count < config.MAX_RETRIES:
        next_retry = retry_count + 1
        log.info("[router] verdict=FAIL  retry %d/%d → retrieve", next_retry, config.MAX_RETRIES)
        # Mutate retry_count in state before looping back
        state["retry_count"] = next_retry
        return "retrieve"

    log.info("[router] verdict=FAIL  max retries (%d) reached → finalize", config.MAX_RETRIES)
    return "finalize"


# ── Graph construction ────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(RAGState)

    # Register nodes
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade_documents", grade_documents)
    graph.add_node("generate", generate)
    graph.add_node("evaluate_answer", evaluate_answer)
    graph.add_node("finalize", finalize)

    # Linear edges
    graph.add_edge("retrieve", "grade_documents")
    graph.add_edge("grade_documents", "generate")
    graph.add_edge("generate", "evaluate_answer")

    # Conditional edge after evaluation
    graph.add_conditional_edges(
        "evaluate_answer",
        _route_after_evaluation,
        {
            "finalize": "finalize",
            "retrieve": "retrieve",   # loops back with rewritten query
        },
    )

    graph.add_edge("finalize", END)

    # Entry point
    graph.set_entry_point("retrieve")

    return graph


def compile_graph():
    """Compile and return the runnable graph."""
    g = build_graph()
    return g.compile()
