# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt   # only dependency is gradio
python app.py                     # runs the Gradio dev server (prints local URL, e.g. http://127.0.0.1:7860)
```

There is no test suite, linter, or build step configured. Gradio auto-reload is not enabled — restart `python app.py` after editing `app.py`, `diff_engine.py`, or `parsers/cisco_ios.py` to see changes (see gotcha below).

To sanity-check the diff logic without the UI:

```bash
python -c "
from diff_engine import compare_configs
print(compare_configs(open('old.cfg').read(), open('new.cfg').read()))
"
```

## Architecture

Three-layer pipeline, kept deliberately decoupled so a new vendor parser can be added without touching the other two layers:

1. **`parsers/cisco_ios.py`** — turns raw config text into an ordered list of `ConfigBlock` (`header`, `block_type`, `lines`). Splits on indentation: a non-indented line matching a known keyword (`interface `, `router `, `ip access-list `, `line `, `vlan `, etc. — see `BLOCK_KEYWORDS`) starts a new named block; indented lines attach to the currently open block; non-indented lines that match nothing (e.g. `hostname`, `enable secret`) collect into one synthetic `__GLOBAL__` block, preserving original order. To support another vendor, add a sibling module exposing the same `parse_config(text) -> list[ConfigBlock]` contract — no changes needed elsewhere.

2. **`diff_engine.py`** — `compare_configs(old_text, new_text) -> DiffResult` is the only entry point. It parses both configs, then aligns blocks **by header string** (not by position), so a reordered or untouched block never shows up as a full rewrite. Blocks present in both are line-diffed with `difflib.SequenceMatcher`; `replace` opcodes are paired positionally into `modified` rows (extra lines on either side become `added`/`removed`). Output order is: new-config block order first (covers unchanged/modified/added blocks), then any old-only (fully removed) blocks appended in their original order. Risk flagging (`RISK_KEYWORDS`: `access-list`, `shutdown`, `no shutdown`, `line vty`, `enable secret`) is checked against both the individual line text *and* the block header — so e.g. an added ACE line inside an `ip access-list ...` block gets flagged even if the line itself doesn't contain the word "access-list".

3. **`app.py`** — Gradio `Blocks` UI. Renders `DiffResult` as a two-column HTML grid (`display: grid; grid-template-columns: 1fr 1fr`), one `.diff-row` div per `DiffRow` with both cells as direct children. The "Download diff report" button writes the same rendered HTML (summary + diff, wrapped in a full `<html>` doc) to a temp file via `tempfile.mkdtemp()`.

### Gotchas learned during development

- **CSS on `.diff-row` (a grid container) must not add generated content.** A `::before`/`::after` rule with `content: ""` on a `display: grid` element becomes a real (empty) grid item and shifts the two real cells into different rows/columns — this exact bug shipped once and silently swapped which column the old/new line appeared in. If you need a decorative marker on `.diff-row`, apply it to a non-grid ancestor or use `outline`/`border` instead of a pseudo-element.
- **`gr.Blocks(css=...)` is deprecated in Gradio 6** — pass `css=` to `demo.launch()` instead (already done in `app.py`).
- **Stale dev server on Windows**: `python app.py` run in the background doesn't always die cleanly when the wrapping shell task is stopped; the orphaned process keeps holding port 7860 and silently serves old code while a new instance binds to 7861+. If edits don't seem to take effect, check `netstat -ano | grep 7860` for a stale PID before assuming the code is wrong.
