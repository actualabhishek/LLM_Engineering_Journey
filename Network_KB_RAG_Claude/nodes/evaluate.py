"""
evaluate_answer node — checks the generated answer for two properties:
  1. Groundedness  — every claim is supported by the graded_docs context
  2. Relevance     — the answer directly addresses the original question

Uses claude-haiku-4-5 with a structured JSON response.
On FAIL, also rewrites the query to improve the next retrieval round.
"""

import json
import logging
import re
import anthropic

import config
from state import RAGState, EvaluationResult

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


_EVAL_PROMPT = """\
You are a quality evaluator for a RAG (retrieval-augmented generation) system.

Original question:
{question}

Context used to generate the answer (the only allowed sources):
\"\"\"
{context}
\"\"\"

Generated answer:
\"\"\"
{answer}
\"\"\"

Evaluate the answer on TWO criteria:

1. GROUNDED: Is every factual claim in the answer supported by the context above?
   Answer YES only if no claim was invented or assumed beyond the context.

2. RELEVANT: Does the answer directly address the original question?

Also provide:
- reason: one sentence summarising why you judged PASS or FAIL
- rewritten_query: if the verdict is FAIL, suggest an improved search query that
  would retrieve better context. Leave empty string if verdict is PASS.

Respond with ONLY a valid JSON object — no markdown fences, no extra text:
{{
  "grounded": true | false,
  "relevant": true | false,
  "verdict": "PASS" | "FAIL",
  "reason": "...",
  "rewritten_query": "..."
}}
"""


def _parse_eval_response(text: str) -> EvaluationResult:
    # Strip any accidental markdown fences
    text = re.sub(r"```(?:json)?", "", text).strip()
    data = json.loads(text)
    return EvaluationResult(
        grounded=bool(data.get("grounded", False)),
        relevant=bool(data.get("relevant", False)),
        verdict=data.get("verdict", "FAIL"),
        reason=data.get("reason", ""),
        rewritten_query=data.get("rewritten_query", ""),
    )


def evaluate_answer(state: RAGState) -> dict:
    question = state["question"]
    answer = state.get("generation", "")
    docs = state.get("graded_docs") or state.get("retrieved_docs", [])

    context = "\n\n---\n\n".join(
        f"[Source: {d.metadata.get('source','?')} | {d.metadata.get('section_heading','?')}]\n{d.page_content}"
        for d in docs
    )

    prompt = _EVAL_PROMPT.format(
        question=question,
        context=context[:6000],  # cap to avoid huge prompts to Haiku
        answer=answer,
    )

    log.info("[evaluate_answer] evaluating answer (retry_count=%d)", state.get("retry_count", 0))

    response = _get_client().messages.create(
        model=config.GRADER_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    try:
        result = _parse_eval_response(raw)
    except (json.JSONDecodeError, KeyError) as exc:
        log.warning("[evaluate_answer] failed to parse response (%s) — defaulting to FAIL", exc)
        result = EvaluationResult(
            grounded=False,
            relevant=False,
            verdict="FAIL",
            reason=f"Parse error: {exc}",
            rewritten_query=question,
        )

    log.info(
        "[evaluate_answer] verdict=%s  grounded=%s  relevant=%s  reason=%s",
        result["verdict"], result["grounded"], result["relevant"], result["reason"],
    )

    updates: dict = {"evaluation": result}
    if result["verdict"] == "FAIL" and result["rewritten_query"]:
        updates["rewritten_query"] = result["rewritten_query"]
        log.info("[evaluate_answer] rewritten query → %r", result["rewritten_query"])

    return updates
