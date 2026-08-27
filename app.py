"""
app.py — Gradio UI for the RAG pipeline.

Run:  python app.py
Then open http://localhost:7860 in your browser.
"""

import queue
import threading
import time

import gradio as gr

from graph import compile_graph
from nodes.generate import set_token_sink
from state import RAGState
import config

# Compile once at startup — not per request
_app = compile_graph()

_PLACEHOLDER = "_Answer will appear here._"
_PLACEHOLDER_SRC = "_Sources will appear here._"
_PLACEHOLDER_META = "_Quality check will appear here._"


def _build_sources_md(sources: list[dict]) -> str:
    seen: set[tuple] = set()
    rows: list[str] = []
    for s in sources:
        key = (s["source"], s["section_heading"])
        if key not in seen:
            seen.add(key)
            rows.append(f"- **{s['source']}** — {s['section_heading']}")
    return "\n".join(rows) if rows else "_No sources retrieved._"


def _build_meta_md(state: dict) -> str:
    evaluation = state.get("evaluation")
    retry_count = state.get("retry_count", 0)
    if not evaluation:
        return "_Evaluation not available._"
    verdict = evaluation.get("verdict", "N/A")
    reason = evaluation.get("reason", "")
    icon = "✅" if verdict == "PASS" else "⚠️"
    rewritten = state.get("rewritten_query", "")
    rewrite_line = f"\n- **Rewritten query:** {rewritten}" if rewritten else ""
    return (
        f"{icon} **Verdict:** {verdict}  \n"
        f"- **Retries used:** {retry_count} / {config.MAX_RETRIES}  \n"
        f"- **Reason:** {reason}"
        f"{rewrite_line}"
    )


def run_query_streaming(question: str):
    """
    Generator function — yields (answer, sources, meta) tuples progressively.

    Phases:
      1. Status updates while retrieve / grade / evaluate run (no LLM tokens yet).
      2. Real-time token streaming from the generate node via set_token_sink().
      3. Final yield with complete answer + sources + quality metadata.
    """
    if not question.strip():
        yield "Please enter a question.", _PLACEHOLDER_SRC, _PLACEHOLDER_META
        return

    token_q: queue.Queue[str | None] = queue.Queue()
    result: dict = {}
    error: list = []

    # ── Pipeline thread ───────────────────────────────────────────────────────

    def _run_pipeline():
        initial_state: RAGState = {
            "question": question.strip(),
            "rewritten_query": "",
            "retrieved_docs": [],
            "graded_docs": [],
            "generation": "",
            "evaluation": None,
            "retry_count": 0,
            "final_answer": "",
            "sources": [],
        }
        try:
            set_token_sink(lambda tok: token_q.put(tok))
            state = _app.invoke(initial_state)
            result["state"] = state
        except Exception as exc:
            error.append(exc)
        finally:
            set_token_sink(None)
            token_q.put(None)  # sentinel — signals end of stream

    thread = threading.Thread(target=_run_pipeline, daemon=True)
    thread.start()

    # ── Phase 1 & 2: stream tokens, show status while waiting ─────────────────

    status_cycle = [
        "_Retrieving relevant documents..._",
        "_Grading document relevance..._",
        "_Generating answer..._",
    ]
    status_idx = 0
    accumulated = ""
    generating = False  # flips True on first token

    while True:
        try:
            token = token_q.get(timeout=1.5)
        except queue.Empty:
            # No token yet — show cycling status message
            if not generating:
                yield status_cycle[status_idx % len(status_cycle)], _PLACEHOLDER_SRC, _PLACEHOLDER_META
                status_idx += 1
            continue

        if token is None:
            break  # pipeline finished

        # First token — switch from status display to live answer display
        generating = True
        accumulated += token
        yield accumulated, _PLACEHOLDER_SRC, _PLACEHOLDER_META
        time.sleep(0.02)  # let Gradio flush each update before the next token

    thread.join()

    # ── Phase 3: final yield with sources + quality metadata ──────────────────

    if error:
        yield f"**Error:** {error[0]}", _PLACEHOLDER_SRC, _PLACEHOLDER_META
        return

    state = result.get("state", {})
    final_answer = state.get("final_answer", accumulated or "No answer produced.")
    sources_md = _build_sources_md(state.get("sources", []))
    meta_md = _build_meta_md(state)

    yield final_answer, sources_md, meta_md


# ── UI layout ─────────────────────────────────────────────────────────────────

with gr.Blocks(title="TCS Network KB — RAG Assistant") as demo:

    gr.Markdown(
        """
        # TCS Network KB — RAG Assistant
        Ask questions about F5 BIG-IP, Cisco Nexus, BGP, SSL certificates, VLANs, and more.
        Powered by **LangGraph** + **Claude** (Opus for generation · Haiku for grading).
        """
    )

    with gr.Row():
        with gr.Column(scale=3):
            question_box = gr.Textbox(
                label="Your question",
                placeholder="e.g. How do I renew an SSL certificate on F5 BIG-IP?",
                lines=2,
                autofocus=True,
            )
            with gr.Row():
                submit_btn = gr.Button("Ask", variant="primary", scale=2)
                clear_btn = gr.Button("Clear", scale=1)

        with gr.Column(scale=1):
            gr.Markdown("### Example questions")
            gr.Examples(
                examples=[
                    ["What is the pre-upgrade checklist for F5 BIG-IP firmware?"],
                    ["How do I renew an SSL certificate on F5 BIG-IP?"],
                    ["What are the BGP troubleshooting steps when a peer goes down?"],
                    ["How do I configure a trunk port on a Cisco Nexus switch?"],
                    ["What should I verify after a Nexus firmware upgrade?"],
                    ["How do I test F5 BIG-IP failover without affecting production?"],
                ],
                inputs=question_box,
            )

    gr.Markdown("---")

    with gr.Row():
        with gr.Column(scale=3):
            answer_out = gr.Markdown(label="Answer", value=_PLACEHOLDER)
        with gr.Column(scale=1):
            sources_out = gr.Markdown(label="Sources", value=_PLACEHOLDER_SRC)
            meta_out = gr.Markdown(label="Quality check", value=_PLACEHOLDER_META)

    # ── Event wiring ──────────────────────────────────────────────────────────

    shared = dict(
        fn=run_query_streaming,
        inputs=question_box,
        outputs=[answer_out, sources_out, meta_out],
    )

    submit_btn.click(**shared)
    question_box.submit(**shared)  # Enter key

    clear_btn.click(
        fn=lambda: (_PLACEHOLDER, _PLACEHOLDER_SRC, _PLACEHOLDER_META, ""),
        outputs=[answer_out, sources_out, meta_out, question_box],
    )


if __name__ == "__main__":
    demo.queue()  # required for generator-based streaming to work
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        inbrowser=True,
        theme=gr.themes.Soft(),
    )
