# Cisco Config Diff Viewer

16 years of staring at Cisco configs taught me one thing: a raw
`diff` on two IOS config files is nearly useless. Reorder a couple of
interfaces and suddenly your "diff" is a wall of red and green that
tells you nothing about what actually changed. This tool is my fix
for that — built hands-on, grounded in the real pain of doing this
work on real networks.

It's a Gradio web app for comparing two Cisco IOS configuration files
(before/after) with a side-by-side, block-aware diff view.

Instead of a raw line-by-line diff, the config is first parsed into
logical sections (`interface ...`, `router ...`, `ip access-list ...`,
`line vty ...`, `vlan ...`, plus a synthetic block for global commands).
Sections are matched between the old and new config by identity, so a
reordered or untouched block doesn't show up as a full rewrite. Within
each matched block, line-level differences are computed with Python's
`difflib.SequenceMatcher`.

## Features

- Upload old/new configs (`.txt`, `.cfg`, `.log`)
- Side-by-side scrollable diff panel:
  - Red / strikethrough = removed lines
  - Green = added lines
  - Amber = modified lines
  - Muted gray = unchanged context lines
- Summary counts of lines added / removed / modified
- Security risk flagging (bold + orange border) for changes touching
  `access-list`, `shutdown` / `no shutdown`, `line vty`, or
  `enable secret`
- Download the full diff as a standalone HTML report

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

Gradio will print a local URL (typically `http://127.0.0.1:7860`) —
open it in a browser, upload both config files, and click **Compare**.

## Project structure

```
CiscoConfigDiffAuditor/
├── app.py              # Gradio UI and HTML rendering
├── diff_engine.py       # Block alignment + difflib-based line diffing
├── parsers/
│   ├── __init__.py
│   └── cisco_ios.py     # Cisco IOS config -> logical blocks
├── requirements.txt
└── README.md
```

## Adding another vendor (e.g. F5, Palo Alto)

The parser layer is isolated in `parsers/`. To support a new vendor:

1. Add `parsers/<vendor>.py` exposing `parse_config(text) -> list[ConfigBlock]`,
   using the same `ConfigBlock` shape (`header`, `block_type`, `lines`).
2. Point `diff_engine.compare_configs` (or a new wrapper) at the
   appropriate parser based on a vendor selection in the UI.

No changes to the diff alignment logic or the Gradio rendering code
should be needed — both operate on the vendor-neutral `ConfigBlock` /
`DiffResult` data structures.

---

This is part of my own transition from network engineering into
AI/ML engineering — I'm learning Python and building real, useful
tools along the way instead of just reading about it. More of the
journey lives at
[LLM_Engineering_Journey](https://github.com/actualabhishek/LLM_Engineering_Journey).

Still learning, still building.
