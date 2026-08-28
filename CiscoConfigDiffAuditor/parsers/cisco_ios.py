"""Cisco IOS configuration parser.

Splits a raw Cisco IOS config into logical blocks (interfaces, routing
processes, ACLs, line configs, VLANs, etc.) plus a synthetic block for
top-level global commands. This lets the diff engine align and compare
blocks by identity instead of doing a naive line-by-line diff of the
whole file.

To support another vendor later, add a sibling module (e.g. f5.py) that
exposes the same `parse_config(text) -> list[ConfigBlock]` contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

GLOBAL_HEADER = "__GLOBAL__"

# Top-level keywords that start a new named block. Order doesn't matter;
# matching is done against the start of a non-indented line.
BLOCK_KEYWORDS: list[tuple[str, str]] = [
    (r"^interface\s+\S+", "interface"),
    (r"^router\s+\S+", "router"),
    (r"^ip\s+access-list\s+\S+.*", "access-list"),
    (r"^ip\s+route\s+.*", "route"),
    (r"^line\s+\S+.*", "line"),
    (r"^vlan\s+\S+", "vlan"),
    (r"^class-map\s+.*", "class-map"),
    (r"^policy-map\s+.*", "policy-map"),
    (r"^crypto\s+.*", "crypto"),
    (r"^route-map\s+.*", "route-map"),
    (r"^ip\s+prefix-list\s+.*", "prefix-list"),
    (r"^spanning-tree\s+.*", "spanning-tree"),
    (r"^aaa\s+.*", "aaa"),
    (r"^banner\s+.*", "banner"),
]

_COMPILED = [(re.compile(pat), kind) for pat, kind in BLOCK_KEYWORDS]


@dataclass
class ConfigBlock:
    header: str
    block_type: str
    lines: list[str] = field(default_factory=list)


def _match_block_start(line: str) -> str | None:
    for pattern, kind in _COMPILED:
        if pattern.match(line):
            return kind
    return None


def parse_config(text: str) -> list[ConfigBlock]:
    """Parse raw Cisco IOS config text into an ordered list of ConfigBlock.

    Order of first appearance is preserved. Indented lines (sub-config
    lines) are attached to the most recently opened block. Non-indented
    lines that don't match a known block keyword are collected into a
    single synthetic global block (in their original relative order).
    """
    blocks: list[ConfigBlock] = []
    global_block = ConfigBlock(header=GLOBAL_HEADER, block_type="global")
    current: ConfigBlock | None = None
    global_inserted = False

    def ensure_global_inserted() -> None:
        nonlocal global_inserted
        if not global_inserted:
            blocks.append(global_block)
            global_inserted = True

    raw_lines = text.splitlines()
    for raw_line in raw_lines:
        if raw_line.strip() == "":
            if current is not None:
                current.lines.append(raw_line)
            continue

        is_indented = raw_line[0] in (" ", "\t")
        stripped = raw_line.strip()

        if is_indented and current is not None:
            current.lines.append(raw_line)
            continue

        # Non-indented line: either starts a new block or is a global command.
        if stripped == "end" or stripped == "!":
            current = None
            continue

        kind = _match_block_start(stripped)
        if kind is not None:
            header = stripped
            current = ConfigBlock(header=header, block_type=kind)
            current.lines.append(raw_line)
            blocks.append(current)
        else:
            ensure_global_inserted()
            global_block.lines.append(raw_line)
            current = None

    return blocks
