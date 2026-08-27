"""
ingest.py — Parse documents → Markdown → chunk → embed → Chroma index.

Supported formats: PDF (.pdf), Word (.docx), plain text (.txt, .md)
Run:  python ingest.py <path-to-file-or-dir>
"""

import argparse
import logging
import os
import re
import sys
import uuid
from pathlib import Path

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_pdf(path: Path) -> str:
    """Convert PDF to Markdown using pymupdf4llm (preserves headings/tables)."""
    try:
        import pymupdf4llm
    except ImportError:
        raise ImportError("Install pymupdf4llm:  pip install pymupdf4llm")
    log.info("Parsing PDF: %s", path.name)
    md = pymupdf4llm.to_markdown(str(path))
    return _clean_markdown(md)


def parse_docx(path: Path) -> str:
    """Convert DOCX to Markdown, mapping paragraph styles to heading levels."""
    try:
        from docx import Document as DocxDocument
        from docx.oxml.ns import qn
    except ImportError:
        raise ImportError("Install python-docx:  pip install python-docx")

    log.info("Parsing DOCX: %s", path.name)
    doc = DocxDocument(str(path))
    lines: list[str] = []

    style_to_prefix = {
        "Heading 1": "# ",
        "Heading 2": "## ",
        "Heading 3": "### ",
        "Heading 4": "#### ",
    }

    for block in doc.element.body:
        tag = block.tag.split("}")[-1]

        if tag == "p":
            # Paragraph
            para_xml = block
            style_name = ""
            style_el = para_xml.find(f".//{qn('w:pStyle')}")
            if style_el is not None:
                style_name = style_el.get(qn("w:val"), "")
                # Normalize e.g. "Heading1" → "Heading 1"
                style_name = re.sub(r"(\D)(\d)", r"\1 \2", style_name)

            text = "".join(node.text or "" for node in para_xml.iter() if node.tag.split("}")[-1] == "t")
            text = text.strip()
            if not text:
                lines.append("")
                continue

            prefix = style_to_prefix.get(style_name, "")
            lines.append(f"{prefix}{text}")

        elif tag == "tbl":
            # Table — convert to Markdown table
            table_lines = _docx_table_to_md(block)
            lines.extend(table_lines)
            lines.append("")

    return _clean_markdown("\n".join(lines))


def _docx_table_to_md(tbl_element) -> list[str]:
    """Convert a DOCX table XML element to Markdown table rows."""
    from docx.oxml.ns import qn

    rows = tbl_element.findall(f".//{qn('w:tr')}")
    md_rows: list[str] = []
    for i, row in enumerate(rows):
        cells = row.findall(f".//{qn('w:tc')}")
        cell_texts = []
        for cell in cells:
            text = "".join(
                node.text or ""
                for node in cell.iter()
                if node.tag.split("}")[-1] == "t"
            ).strip()
            cell_texts.append(text)
        md_rows.append("| " + " | ".join(cell_texts) + " |")
        if i == 0:
            md_rows.append("|" + "|".join(["---"] * len(cell_texts)) + "|")
    return md_rows


def parse_text(path: Path) -> str:
    """Read plain text / Markdown files as-is."""
    log.info("Reading text file: %s", path.name)
    return path.read_text(encoding="utf-8", errors="replace")


def _clean_markdown(md: str) -> str:
    """Strip page headers/footers patterns and normalize whitespace."""
    # Remove common PDF header/footer artifacts (page numbers, repeated titles)
    md = re.sub(r"(?m)^[-_]{3,}\s*$", "", md)          # horizontal rules
    md = re.sub(r"(?m)^\s*Page\s+\d+\s*$", "", md, flags=re.IGNORECASE)
    md = re.sub(r"\n{3,}", "\n\n", md)                  # collapse blank lines
    return md.strip()


# ── Dispatch ──────────────────────────────────────────────────────────────────

PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".txt": parse_text,
    ".md": parse_text,
}


def parse_file(path: Path) -> str:
    ext = path.suffix.lower()
    parser = PARSERS.get(ext)
    if parser is None:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {list(PARSERS)}")
    return parser(path)


# ── Chunking ──────────────────────────────────────────────────────────────────

# Headers to split on (order matters — largest → smallest)
_HEADER_SPLITS = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
]


def chunk_markdown(markdown: str, source_name: str) -> list[Document]:
    """
    Split Markdown respecting heading boundaries first, then by token count.

    Strategy:
      1. MarkdownHeaderTextSplitter produces semantically coherent sections.
      2. RecursiveCharacterTextSplitter further splits oversized sections so
         no chunk exceeds CHUNK_SIZE characters.
    """
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_HEADER_SPLITS,
        strip_headers=False,  # keep headings in chunk text for context
    )
    header_chunks = header_splitter.split_text(markdown)

    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    final_docs: list[Document] = []
    for i, hchunk in enumerate(header_chunks):
        sub_docs = char_splitter.split_documents([hchunk])
        for j, doc in enumerate(sub_docs):
            # Build rich metadata
            section_heading = (
                doc.metadata.get("h1", "")
                or doc.metadata.get("h2", "")
                or doc.metadata.get("h3", "")
                or "root"
            )
            doc.metadata.update(
                {
                    "source": source_name,
                    "section_heading": section_heading,
                    "chunk_id": f"{source_name}::section{i}::chunk{j}",
                    "chunk_index": len(final_docs),
                }
            )
            final_docs.append(doc)

    log.info("  → %d chunks from '%s'", len(final_docs), source_name)
    return final_docs


# ── Chroma indexing ───────────────────────────────────────────────────────────

def get_vectorstore() -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
    return Chroma(
        collection_name=config.COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=config.CHROMA_DIR,
    )


def index_documents(docs: list[Document]) -> None:
    log.info("Indexing %d chunks into Chroma ('%s') …", len(docs), config.CHROMA_DIR)
    vs = get_vectorstore()
    # Assign stable UUIDs as Chroma document IDs
    ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, d.metadata["chunk_id"])) for d in docs]
    vs.add_documents(docs, ids=ids)
    log.info("Indexing complete.")


# ── Save parsed Markdown ──────────────────────────────────────────────────────

def save_markdown(markdown: str, source_path: Path) -> Path:
    out_dir = Path(config.PARSED_DIR)
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / (source_path.stem + ".md")
    out_path.write_text(markdown, encoding="utf-8")
    log.info("Saved Markdown → %s", out_path)
    return out_path


# ── Orchestration ─────────────────────────────────────────────────────────────

def ingest_file(path: Path) -> None:
    markdown = parse_file(path)
    save_markdown(markdown, path)
    docs = chunk_markdown(markdown, source_name=path.name)
    index_documents(docs)


def ingest_path(target: str) -> None:
    p = Path(target)
    if p.is_file():
        ingest_file(p)
    elif p.is_dir():
        files = [f for f in p.rglob("*") if f.suffix.lower() in PARSERS]
        if not files:
            log.warning("No supported files found in %s", p)
            return
        for f in files:
            ingest_file(f)
    else:
        raise FileNotFoundError(f"Path not found: {target}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest documents into Chroma RAG index")
    parser.add_argument("path", help="File or directory to ingest")
    args = parser.parse_args()
    ingest_path(args.path)
