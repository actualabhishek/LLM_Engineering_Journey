"""Cisco Config Diff Viewer — Gradio app.

Upload two Cisco IOS config files and see a side-by-side, block-aware
diff with add/remove/modify highlighting and security-risk flagging.

Run with: python app.py
"""

from __future__ import annotations

import html
import tempfile
from pathlib import Path

import gradio as gr

from diff_engine import DiffResult, compare_configs

CUSTOM_CSS = """
.diff-summary {
    display: flex;
    gap: 1.5rem;
    font-family: "Segoe UI", sans-serif;
    font-size: 1rem;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    background: var(--block-background-fill, #f5f5f5);
    margin-bottom: 0.5rem;
}
.diff-summary .stat { font-weight: 600; }
.stat-added { color: #1e8e3e; }
.stat-removed { color: #d93025; }
.stat-modified { color: #b06000; }

.diff-container {
    max-height: 640px;
    overflow-y: auto;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 0.85rem;
}
.diff-header-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    background: #37474f;
    color: #eceff1;
    font-weight: bold;
    position: sticky;
    top: 0;
    z-index: 1;
}
.diff-header-row > div { padding: 6px 10px; }

.diff-block-title {
    grid-column: 1 / span 2;
    background: #cfd8dc;
    color: #263238;
    font-weight: bold;
    padding: 4px 10px;
    border-top: 1px solid #b0bec5;
    border-bottom: 1px solid #b0bec5;
}

.diff-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    border-bottom: 1px solid #eee;
}
.diff-row > div {
    padding: 2px 10px;
    white-space: pre-wrap;
    word-break: break-word;
    border-left: 1px solid #eee;
}
.diff-row > div:first-child { border-left: none; }

.diff-row.equal > div { color: #757575; }
.diff-row.removed .old-cell { background: #fde8e8; color: #7a1f1f; text-decoration: line-through; }
.diff-row.removed .new-cell { background: #fafafa; }
.diff-row.added .new-cell { background: #e6f4ea; color: #14532d; }
.diff-row.added .old-cell { background: #fafafa; }
.diff-row.modified .old-cell { background: #fff3cd; color: #7a5b00; }
.diff-row.modified .new-cell { background: #fff3cd; color: #7a5b00; }

.diff-row.risky > div { font-weight: bold; border-top: 2px solid #ff8c00; border-bottom: 2px solid #ff8c00; }
"""

RISK_BADGE = (
    '<span style="color:#ff8c00; font-weight:bold; margin-right:4px;" '
    'title="Security-sensitive change">&#9888;</span>'
)


def _esc(text: str | None) -> str:
    if text is None:
        return ""
    return html.escape(text)


def _render_summary(result: DiffResult) -> str:
    return (
        '<div class="diff-summary">'
        f'<div class="stat stat-added">{result.added} lines added</div>'
        f'<div class="stat stat-removed">{result.removed} lines removed</div>'
        f'<div class="stat stat-modified">{result.modified} lines modified</div>'
        "</div>"
    )


def _render_diff_html(result: DiffResult) -> str:
    parts = [
        '<div class="diff-container">',
        '<div class="diff-header-row"><div>Old Configuration</div><div>New Configuration</div></div>',
    ]
    for block in result.blocks:
        title = _esc(block.header)
        parts.append(f'<div class="diff-block-title">{title}</div>')
        for row in block.rows:
            classes = ["diff-row", row.status]
            if row.risky:
                classes.append("risky")
            badge = RISK_BADGE if row.risky else ""
            old_cell = _esc(row.old_line) if row.old_line is not None else "&nbsp;"
            new_cell = _esc(row.new_line) if row.new_line is not None else "&nbsp;"
            parts.append(
                f'<div class="{" ".join(classes)}">'
                f'<div class="old-cell">{badge if row.status in ("removed", "modified") else ""}{old_cell}</div>'
                f'<div class="new-cell">{badge if row.status in ("added",) else ""}{new_cell}</div>'
                "</div>"
            )
    parts.append("</div>")
    return "".join(parts)


def _build_report_html(summary_html: str, diff_html: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Cisco Config Diff Report</title>"
        f"<style>{CUSTOM_CSS}</style></head><body>"
        "<h2>Cisco Config Diff Report</h2>"
        f"{summary_html}{diff_html}"
        "</body></html>"
    )


def _read_upload(file_obj) -> str:
    path = Path(file_obj.name if hasattr(file_obj, "name") else file_obj)
    return path.read_text(encoding="utf-8", errors="replace")


def on_compare(old_file, new_file):
    if old_file is None or new_file is None:
        empty = '<div class="diff-summary">Please upload both configuration files.</div>'
        return empty, "", gr.update(value=None, visible=False)

    old_text = _read_upload(old_file)
    new_text = _read_upload(new_file)

    result = compare_configs(old_text, new_text)
    summary_html = _render_summary(result)
    diff_html = _render_diff_html(result)

    report_html = _build_report_html(summary_html, diff_html)
    tmp_dir = Path(tempfile.mkdtemp(prefix="cisco_diff_"))
    report_path = tmp_dir / "cisco_config_diff_report.html"
    report_path.write_text(report_html, encoding="utf-8")

    return summary_html, diff_html, gr.update(value=str(report_path), visible=True)


with gr.Blocks(title="Cisco Config Diff Viewer") as demo:
    gr.Markdown("# Cisco Config Diff Viewer")
    gr.Markdown(
        "Upload an old and new Cisco IOS configuration to see a side-by-side, "
        "block-aware diff. Security-sensitive changes (ACLs, `shutdown`, "
        "`line vty`, `enable secret`) are flagged with &#9888;."
    )

    with gr.Row():
        old_file_input = gr.File(
            label="Old Configuration",
            file_types=[".txt", ".cfg", ".log"],
        )
        new_file_input = gr.File(
            label="New Configuration",
            file_types=[".txt", ".cfg", ".log"],
        )

    compare_btn = gr.Button("Compare", variant="primary")

    summary_output = gr.HTML()
    diff_output = gr.HTML()
    download_output = gr.DownloadButton(label="Download diff report", visible=False)

    compare_btn.click(
        fn=on_compare,
        inputs=[old_file_input, new_file_input],
        outputs=[summary_output, diff_output, download_output],
    )


if __name__ == "__main__":
    demo.launch(css=CUSTOM_CSS, share=True)
