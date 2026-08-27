"""Block-aware diff engine for Cisco IOS configs.

Parses old/new config text into logical blocks (via parsers.cisco_ios),
aligns blocks by header identity, then runs difflib.SequenceMatcher on
the line lists within each aligned block. This means a reordered
interface block (same header, same content, different position in the
file) is compared to its counterpart rather than showing up as a
wholesale add+remove.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from parsers.cisco_ios import ConfigBlock, parse_config

RISK_KEYWORDS = [
    "access-list",
    "no shutdown",
    "shutdown",
    "line vty",
    "enable secret",
]


@dataclass
class DiffRow:
    old_line: str | None
    new_line: str | None
    status: str  # "equal" | "added" | "removed" | "modified" | "header"
    risky: bool = False


@dataclass
class BlockDiff:
    header: str
    rows: list[DiffRow] = field(default_factory=list)


@dataclass
class DiffResult:
    blocks: list[BlockDiff] = field(default_factory=list)
    added: int = 0
    removed: int = 0
    modified: int = 0


def _is_risky(*lines: str | None) -> bool:
    for line in lines:
        if not line:
            continue
        lowered = line.lower()
        if any(keyword in lowered for keyword in RISK_KEYWORDS):
            return True
    return False


def _diff_block_lines(old_lines: list[str], new_lines: list[str]) -> list[DiffRow]:
    rows: list[DiffRow] = []
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for old_l, new_l in zip(old_lines[i1:i2], new_lines[j1:j2]):
                rows.append(DiffRow(old_line=old_l, new_line=new_l, status="equal"))
        elif tag == "delete":
            for old_l in old_lines[i1:i2]:
                rows.append(
                    DiffRow(old_line=old_l, new_line=None, status="removed", risky=_is_risky(old_l))
                )
        elif tag == "insert":
            for new_l in new_lines[j1:j2]:
                rows.append(
                    DiffRow(old_line=None, new_line=new_l, status="added", risky=_is_risky(new_l))
                )
        elif tag == "replace":
            old_chunk = old_lines[i1:i2]
            new_chunk = new_lines[j1:j2]
            paired = min(len(old_chunk), len(new_chunk))
            for k in range(paired):
                old_l, new_l = old_chunk[k], new_chunk[k]
                rows.append(
                    DiffRow(
                        old_line=old_l,
                        new_line=new_l,
                        status="modified",
                        risky=_is_risky(old_l, new_l),
                    )
                )
            for old_l in old_chunk[paired:]:
                rows.append(
                    DiffRow(old_line=old_l, new_line=None, status="removed", risky=_is_risky(old_l))
                )
            for new_l in new_chunk[paired:]:
                rows.append(
                    DiffRow(old_line=None, new_line=new_l, status="added", risky=_is_risky(new_l))
                )

    return rows


def compare_configs(old_text: str, new_text: str) -> DiffResult:
    old_blocks = parse_config(old_text)
    new_blocks = parse_config(new_text)

    old_by_header: dict[str, ConfigBlock] = {b.header: b for b in old_blocks}
    new_by_header: dict[str, ConfigBlock] = {b.header: b for b in new_blocks}

    result = DiffResult()
    seen_headers: set[str] = set()

    def record_rows(header: str, rows: list[DiffRow]) -> None:
        header_risky = _is_risky(header)
        for row in rows:
            if header_risky and row.status != "equal":
                row.risky = True
        for row in rows:
            if row.status == "added":
                result.added += 1
            elif row.status == "removed":
                result.removed += 1
            elif row.status == "modified":
                result.modified += 1
        result.blocks.append(BlockDiff(header=header, rows=rows))

    # New-config order first: unchanged/modified blocks and wholly new blocks.
    for block in new_blocks:
        header = block.header
        seen_headers.add(header)
        old_block = old_by_header.get(header)
        if old_block is None:
            rows = [
                DiffRow(old_line=None, new_line=l, status="added", risky=_is_risky(l))
                for l in block.lines
            ]
        else:
            rows = _diff_block_lines(old_block.lines, block.lines)
        record_rows(header, rows)

    # Old-only blocks (removed entirely), appended in original old order.
    for block in old_blocks:
        if block.header in seen_headers:
            continue
        rows = [
            DiffRow(old_line=l, new_line=None, status="removed", risky=_is_risky(l))
            for l in block.lines
        ]
        record_rows(block.header, rows)

    return result
