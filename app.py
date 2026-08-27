"""
app.py — Gradio UI for the RAG pipeline.

Run:  python app.py
Then open http://localhost:7860 in your browser.
"""

import gradio as gr
from graph import compile_graph
from state import RAGState
import config

# Compile once at startup — not per request
_app = compile_graph()


def run_query(question: str):
    """Called by Gradio on every submit. Returns (answer_md, sources_md, meta_md)."""
    if not question.strip():
        return "Please enter a question.", "", ""

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
        state = _app.invoke(initial_state)
    except Exception as exc:
        return f"**Error:** {exc}", "", ""

    # ── Answer ────────────────────────────────────────────────────────────────
    answer_md = state.get("final_answer", "No answer produced.")

    # ── Sources ───────────────────────────────────────────────────────────────
    sources = state.get("sources", [])
    if sources:
        seen = set()
        rows = []
        for s in sources:
            key = (s["source"], s["section_heading"])
            if key not in seen:
                seen.add(key)
                rows.append(f"- **{s['source']}** — {s['section_heading']}")
        sources_md = "\n".join(rows)
    else:
        sources_md = "_No sources retrieved._"

    # ── Quality metadata ──────────────────────────────────────────────────────
    evaluation = state.get("evaluation")
    retry_count = state.get("retry_count", 0)
    if evaluation:
        verdict = evaluation.get("verdict", "N/A")
        reason = evaluation.get("reason", "")
        icon = "✅" if verdict == "PASS" else "⚠️"
        rewritten = state.get("rewritten_query", "")
        rewrite_line = f"\n- **Rewritten query:** {rewritten}" if rewritten else ""
        meta_md = (
            f"{icon} **Verdict:** {verdict}  \n"
            f"- **Retries used:** {retry_count} / {config.MAX_RETRIES}  \n"
            f"- **Reason:** {reason}"
            f"{rewrite_line}"
        )
    else:
        meta_md = "_Evaluation not available._"

    return answer_md, sources_md, meta_md


# ── UI layout ─────────────────────────────────────────────────────────────────

with gr.Blocks(title="TCS Network KB — RAG Assistant") as demo:

    gr.Markdown(
        """
        # TCS Network KB — RAG Assistant
        Ask questions about F5 BIG-IP, Cisco Nexus, BGP, SSL certificates, VLANs, and more.
        Powered by **LangGraph** + **Claude** (Opus for generation, Haiku for grading).
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
            examples = gr.Examples(
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
            answer_out = gr.Markdown(
                label="Answer",
                value="_Answer will appear here._",
                elem_classes=["answer-box"],
            )
        with gr.Column(scale=1):
            sources_out = gr.Markdown(label="Sources", value="_Sources will appear here._")
            meta_out = gr.Markdown(label="Quality check", value="_Quality check will appear here._")

    # ── Event wiring ──────────────────────────────────────────────────────────

    submit_btn.click(
        fn=run_query,
        inputs=question_box,
        outputs=[answer_out, sources_out, meta_out],
    )

    question_box.submit(          # Enter key also submits
        fn=run_query,
        inputs=question_box,
        outputs=[answer_out, sources_out, meta_out],
    )

    clear_btn.click(
        fn=lambda: ("_Answer will appear here._", "_Sources will appear here._", "_Quality check will appear here._", ""),
        outputs=[answer_out, sources_out, meta_out, question_box],
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        inbrowser=True,
        theme=gr.themes.Soft(),
    )
