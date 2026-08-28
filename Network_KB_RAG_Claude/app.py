"""
app.py — Gradio UI for the RAG pipeline.

Run:  python app.py
Opens http://localhost:7860 in Chrome or Edge automatically.
"""

import subprocess
import sys
import anthropic
import gradio as gr

from nodes.retrieve import retrieve
from nodes.grade import grade_documents
from nodes.evaluate import evaluate_answer
from nodes.finalize import finalize
from nodes.generate import format_context, SYSTEM_PROMPT, USER_TEMPLATE, _get_client
from state import RAGState
import config

_PLACEHOLDER      = "_Answer will appear here._"
_PLACEHOLDER_SRC  = "_Sources will appear here._"
_PLACEHOLDER_META = "_Quality check will appear here._"


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    icon = "✅" if verdict == "PASS" else "⚠️"
    rewritten = state.get("rewritten_query", "")
    rewrite_line = f"\n- **Rewritten query:** {rewritten}" if rewritten else ""
    return (
        f"{icon} **Verdict:** {verdict}  \n"
        f"- **Retries used:** {retry_count} / {config.MAX_RETRIES}  \n"
        f"- **Reason:** {evaluation.get('reason', '')}"
        f"{rewrite_line}"
    )


def _stream_generate(state: dict):
    """
    Generator: streams tokens directly from Claude and yields (partial_answer,).
    Caller is responsible for updating full state['generation'] after exhaustion.
    """
    question = state.get("rewritten_query") or state["question"]
    docs = state.get("graded_docs") or state.get("retrieved_docs", [])

    if not docs:
        msg = "_No relevant documents found in the knowledge base._"
        state["generation"] = msg
        yield msg
        return

    context = format_context(docs)
    user_msg = USER_TEMPLATE.format(question=question, context=context)

    parts: list[str] = []
    with _get_client().messages.stream(
        model=config.GENERATOR_MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        for token in stream.text_stream:
            parts.append(token)
            yield "".join(parts)

    state["generation"] = "".join(parts).strip()


# ── Main streaming generator ──────────────────────────────────────────────────

def run_query_streaming(question: str):
    """
    Gradio generator — yields (answer, sources, meta) tuples.
    Nodes are called directly (no LangGraph invocation) so we can
    yield between each stage and stream Claude tokens inline.
    """
    if not question.strip():
        yield "Please enter a question.", _PLACEHOLDER_SRC, _PLACEHOLDER_META
        return

    state: RAGState = {
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
        for attempt in range(config.MAX_RETRIES + 1):
            state["retry_count"] = attempt

            # ── Retrieve ──────────────────────────────────────────────────────
            yield "_🔍 Retrieving relevant documents..._", _PLACEHOLDER_SRC, _PLACEHOLDER_META
            state.update(retrieve(state))

            # ── Grade ─────────────────────────────────────────────────────────
            yield "_📋 Grading document relevance..._", _PLACEHOLDER_SRC, _PLACEHOLDER_META
            state.update(grade_documents(state))

            # ── Generate (streaming) ──────────────────────────────────────────
            yield "_✍️ Generating answer..._", _PLACEHOLDER_SRC, _PLACEHOLDER_META
            for partial in _stream_generate(state):
                yield partial, _PLACEHOLDER_SRC, _PLACEHOLDER_META

            # ── Evaluate ──────────────────────────────────────────────────────
            current_answer = state.get("generation", "")
            yield current_answer + "\n\n_📊 Evaluating answer quality..._", _PLACEHOLDER_SRC, _PLACEHOLDER_META
            state.update(evaluate_answer(state))

            evaluation = state.get("evaluation", {})
            if evaluation.get("verdict") == "PASS":
                break

            if attempt < config.MAX_RETRIES:
                rewritten = state.get("rewritten_query", "")
                yield (
                    current_answer + f"\n\n_🔄 Retrying with improved query (attempt {attempt + 1}/{config.MAX_RETRIES})..._",
                    _PLACEHOLDER_SRC,
                    _PLACEHOLDER_META,
                )

        # ── Finalize ──────────────────────────────────────────────────────────
        state.update(finalize(state))
        yield (
            state.get("final_answer", current_answer),
            _build_sources_md(state.get("sources", [])),
            _build_meta_md(state),
        )

    except Exception as exc:
        yield f"**Error:** {exc}", _PLACEHOLDER_SRC, _PLACEHOLDER_META


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
                clear_btn  = gr.Button("Clear", scale=1)

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
            sources_out = gr.Markdown(label="Sources",        value=_PLACEHOLDER_SRC)
            meta_out    = gr.Markdown(label="Quality check",  value=_PLACEHOLDER_META)

    shared = dict(
        fn=run_query_streaming,
        inputs=question_box,
        outputs=[answer_out, sources_out, meta_out],
    )
    submit_btn.click(**shared)
    question_box.submit(**shared)

    clear_btn.click(
        fn=lambda: (_PLACEHOLDER, _PLACEHOLDER_SRC, _PLACEHOLDER_META, ""),
        outputs=[answer_out, sources_out, meta_out, question_box],
    )


# ── Launch ────────────────────────────────────────────────────────────────────

def _open_browser(url: str) -> None:
    """Try Chrome, then Edge, then system default."""
    browsers = [
        ["cmd", "/c", "start", "chrome", url],
        ["cmd", "/c", "start", "msedge", url],
    ]
    for cmd in browsers:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            continue
    # fallback
    import webbrowser
    webbrowser.open(url)


if __name__ == "__main__":
    PORT = 7860
    demo.queue()
    _, _, _ = demo.launch(
        server_name="0.0.0.0",
        server_port=PORT,
        show_error=True,
        inbrowser=False,        # we open the browser ourselves
        prevent_thread_lock=True,
    )
    _open_browser(f"http://localhost:{PORT}")
    # Keep process alive
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down.")
        sys.exit(0)
