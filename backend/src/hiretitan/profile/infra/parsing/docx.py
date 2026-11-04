"""Read the text of a DOCX (FR-004, research R8).

Body paragraphs in document order, tables row by row (cells joined with `` | ``), headers
first and footers last, text boxes (``w:txbxContent``, which python-docx does not expose) and
list paragraphs as bullet lines. DOCX has no visible/hidden distinction handled here.
"""

from __future__ import annotations

import io
from typing import Any, Final

from docx import Document
from docx.oxml.ns import qn

from hiretitan.profile.infra.parsing.types import ParsedDocument, status_for

BULLET: Final = "•"


def _own_text(paragraph: Any) -> str:
    """Text of a paragraph's own runs, leaving out text boxes nested inside it."""
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == qn("w:t") and not _inside_textbox(node, paragraph):
            parts.append(node.text or "")
        elif node.tag == qn("w:tab") and not _inside_textbox(node, paragraph):
            parts.append(" ")
        elif node.tag == qn("w:br") and not _inside_textbox(node, paragraph):
            parts.append("\n")
    return "".join(parts)


def _inside_textbox(node: Any, boundary: Any) -> bool:
    parent = node.getparent()
    while parent is not None and parent is not boundary:
        if parent.tag == qn("w:txbxContent"):
            return True
        parent = parent.getparent()
    return False


def _is_list(paragraph: Any) -> bool:
    properties = paragraph.find(qn("w:pPr"))
    if properties is None:
        return False
    if properties.find(qn("w:numPr")) is not None:
        return True
    style = properties.find(qn("w:pStyle"))
    name = (style.get(qn("w:val")) if style is not None else "") or ""
    return name.lower().startswith(("listbullet", "listnumber", "listparagraph"))


def _paragraph_lines(paragraph: Any) -> list[str]:
    lines: list[str] = []
    text = _own_text(paragraph).strip()
    if text:
        lines.append(f"{BULLET} {text}" if _is_list(paragraph) else text)
    # Text boxes: each inner paragraph is a line. AlternateContent repeats the same box in
    # its Choice and Fallback, so identical neighbours are dropped.
    for inner in paragraph.iter(qn("w:txbxContent")):
        for box_paragraph in inner.iter(qn("w:p")):
            box_text = _own_text(box_paragraph).strip()
            if box_text and (not lines or lines[-1] != box_text):
                lines.append(box_text)
    return lines


def _table_lines(table: Any) -> list[str]:
    lines: list[str] = []
    for row in table.iter(qn("w:tr")):
        cells: list[str] = []
        for cell in row.findall(qn("w:tc")):
            text = " ".join(t for p in cell.iter(qn("w:p")) if (t := _own_text(p).strip()))
            if text:
                cells.append(text)
        if cells:
            lines.append(" | ".join(cells))
    return lines


def _block_lines(container: Any) -> list[str]:
    lines: list[str] = []
    for child in container:
        if child.tag == qn("w:p"):
            lines.extend(_paragraph_lines(child))
        elif child.tag == qn("w:tbl"):
            lines.extend(_table_lines(child))
    return lines


def parse_docx(data: bytes) -> ParsedDocument:
    document = Document(io.BytesIO(data))
    headers: list[str] = []
    footers: list[str] = []
    for section in document.sections:
        for header in (section.header, section.first_page_header, section.even_page_header):
            headers.extend(_block_lines(header._element))
        for footer in (section.footer, section.first_page_footer, section.even_page_footer):
            footers.extend(_block_lines(footer._element))
    body = _block_lines(document.element.body)
    lines: list[str] = []
    for line in [*headers, *body, *footers]:
        if not lines or lines[-1] != line or line.startswith(BULLET):
            lines.append(line)
    text = "\n".join(lines).strip()
    return ParsedDocument(visible_text=text, page_count=None, status=status_for(text))
