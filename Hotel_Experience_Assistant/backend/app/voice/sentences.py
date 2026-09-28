import re

_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT_RE.split(text.strip()) if s.strip()]
