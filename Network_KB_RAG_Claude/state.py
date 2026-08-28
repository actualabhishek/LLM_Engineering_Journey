"""Shared TypedDict state that flows through the LangGraph pipeline."""

from typing import Optional
from typing_extensions import TypedDict
from langchain_core.documents import Document


class EvaluationResult(TypedDict):
    grounded: bool       # every claim is supported by the retrieved context
    relevant: bool       # answer directly addresses the question
    verdict: str         # "PASS" | "FAIL"
    reason: str          # one-sentence explanation
    rewritten_query: str # non-empty only when verdict == "FAIL"


class RAGState(TypedDict):
    question: str
    rewritten_query: str               # set by evaluate_answer on retry
    retrieved_docs: list[Document]
    graded_docs: list[Document]
    generation: str
    evaluation: Optional[EvaluationResult]
    retry_count: int
    final_answer: str
    sources: list[dict]                # [{source, section_heading, chunk_id}]
