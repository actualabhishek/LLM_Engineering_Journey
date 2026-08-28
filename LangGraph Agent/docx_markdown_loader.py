"""
docx_markdown_loader.py

Custom loader that converts a .docx file into Markdown text, preserving
tables as Markdown pipe-tables instead of flattening them into loose text.

Why this exists:
Docx2txtLoader (and python-docx's plain .text extraction) flatten tables
into sequential text with no column association. For SOP/runbook style
documents (commands + expected results in table rows), this severs the
link between a command and its pass/fail criteria once the text gets
chunked. Converting tables to Markdown keeps each row's cells visually
and semantically grouped, so a chunk boundary is far less likely to
separate a command from its expected result.

Returns a LangChain-compatible list[Document] so it drops straight into
the existing pipeline in place of Docx2txtLoader.
"""

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from langchain_core.documents import Document as LCDocument


def _iter_block_items(doc: DocxDocument):
    """
    Walk the document body in order, yielding each paragraph or table
    as it actually appears (not grouped separately). python-docx does
    not provide this directly, so we walk the underlying XML body.

    Returns: generator of Paragraph or Table objects, return type per item.
    """
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag.endswith('}p'):
            yield Paragraph(child, doc)
        elif child.tag.endswith('}tbl'):
            yield Table(child, doc)


def _table_to_markdown(table: Table) -> str:
    """
    Convert a python-docx Table into a Markdown pipe-table string.

    Returns: str, the table rendered as Markdown (header row, separator
    row, then data rows). Empty cells are rendered as empty strings.
    """
    rows = table.rows
    if len(rows) == 0:
        return ""

    lines = []

    # Header row (first row of the table)
    header_cells = [cell.text.strip().replace("\n", " ") for cell in rows[0].cells]
    lines.append("| " + " | ".join(header_cells) + " |")
    lines.append("| " + " | ".join(["---"] * len(header_cells)) + " |")

    # Data rows
    for row in rows[1:]:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def load_docx_as_markdown(path: str) -> list[LCDocument]:
    """
    Load a .docx file and return its content as a single LangChain
    Document, with tables rendered as Markdown pipe-tables and
    paragraphs left as plain text.

    Args:
        path: str, filesystem path to the .docx file

    Returns:
        list[LCDocument], a single-item list matching LangChain loader
        conventions (same shape as Docx2txtLoader().load()), so this
        function is a drop-in replacement.
    """
    doc = DocxDocument(path)
    output_blocks = []

    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                # Preserve heading level as Markdown heading if it's a
                # Word heading style, so later chunking can use "\n\n"
                # / "\n#" boundaries more meaningfully.
                style_name = block.style.name if block.style else ""
                if style_name.startswith("Heading 1"):
                    output_blocks.append(f"# {text}")
                elif style_name.startswith("Heading 2"):
                    output_blocks.append(f"## {text}")
                elif style_name.startswith("Heading 3"):
                    output_blocks.append(f"### {text}")
                else:
                    output_blocks.append(text)
        elif isinstance(block, Table):
            md_table = _table_to_markdown(block)
            if md_table:
                output_blocks.append(md_table)

    full_text = "\n\n".join(output_blocks)

    return [
        LCDocument(
            page_content=full_text,
            metadata={"source": path.split("/")[-1]},
        )
    ]


if __name__ == "__main__":
    # Quick manual test when run directly
    import sys
    test_path = sys.argv[1] if len(sys.argv) > 1 else "TCS_Network_KB_SOPs.docx"
    result = load_docx_as_markdown(test_path)
    print(f"Loaded {len(result)} document(s)")
    print(f"Total length: {len(result[0].page_content)} characters")
    print("--- First 2000 characters ---")
    print(result[0].page_content[:2000])
