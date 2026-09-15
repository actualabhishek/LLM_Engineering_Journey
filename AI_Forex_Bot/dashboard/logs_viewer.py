"""
dashboard/logs_viewer.py
-------------------------
Surfaces storage/logs/execution.log and errors.log in the dashboard — these
were collected all along but never shown anywhere. execution.log can grow
to tens of MB, so this tails from the end of the file rather than reading it
whole.
"""

from pathlib import Path
from typing import List

ROOT = Path(__file__).parent.parent
LOGS_DIR = ROOT / "storage" / "logs"

AVAILABLE_LOGS = {
    "execution.log": LOGS_DIR / "execution.log",
    "errors.log": LOGS_DIR / "errors.log",
}


def tail_lines(path: Path, max_lines: int = 300, chunk_size: int = 65536) -> List[str]:
    """Read up to `max_lines` from the end of a file without loading it whole."""
    if not path.exists():
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            pos = f.tell()
            data = b""
            newline_count = 0
            while pos > 0 and newline_count <= max_lines:
                read_size = min(chunk_size, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size)
                data = chunk + data
                newline_count = data.count(b"\n")
            text = data.decode("utf-8", errors="replace")
            return text.splitlines()[-max_lines:]
    except Exception:
        return []


def filter_lines(lines: List[str], level: str = "ALL", search: str = "") -> List[str]:
    out = lines
    if level and level != "ALL":
        out = [l for l in out if f"| {level}" in l]
    if search:
        s = search.lower()
        out = [l for l in out if s in l.lower()]
    return out
