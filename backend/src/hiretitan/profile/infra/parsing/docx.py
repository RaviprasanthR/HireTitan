"""Read the text of a DOCX (FR-004, research R8).

Body paragraphs in document order, tables row by row (cells joined with `` | ``), headers
first and footers last, text boxes (``w:txbxContent``, which python-docx does not expose) and
list paragraphs as bullet lines.

Text a person cannot see is kept out of the visible text and reported as a hidden run (like
the PDF reader does): runs marked hidden (``w:vanish``), under 4 pt, or coloured like their
background. The background is the run's, paragraph's or table cell's shading, else white, so
white text on a dark banner is normal text.
"""

from __future__ import annotations

import io
import re
from typing import Any, Final

from docx import Document
from docx.oxml.ns import qn

from hiretitan.platform.untrusted.hidden_text import (
    MAX_DELTA_E,
    MIN_VISIBLE_SIZE,
    WHITE,
    HiddenRun,
    Rgb,
    delta_e,
)
from hiretitan.profile.infra.parsing.types import ParsedDocument, status_for

BULLET: Final = "•"


_OFF: Final = ("0", "false", "off")
_HEX: Final = re.compile(r"[0-9A-Fa-f]{6}")


def _hex_rgb(value: str | None) -> Rgb | None:
    if value is None or not _HEX.fullmatch(value):
        return None
    return (int(value[0:2], 16) / 255, int(value[2:4], 16) / 255, int(value[4:6], 16) / 255)


def _fill(properties: Any) -> Rgb | None:
    shading = properties.find(qn("w:shd")) if properties is not None else None
    return _hex_rgb(shading.get(qn("w:fill"))) if shading is not None else None


def _background(run: Any) -> Rgb:
    """The shading behind a run: its own, its paragraph's, its table cell's, else white."""
    if (own := _fill(run.find(qn("w:rPr")))) is not None:
        return own
    node = run.getparent()
    while node is not None:
        if node.tag == qn("w:p") and (fill := _fill(node.find(qn("w:pPr")))) is not None:
            return fill
        if node.tag == qn("w:tc") and (fill := _fill(node.find(qn("w:tcPr")))) is not None:
            return fill
        node = node.getparent()
    return WHITE


def _run_hidden(run: Any) -> bool:
    properties = run.find(qn("w:rPr"))
    if properties is None:
        return False
    vanish = properties.find(qn("w:vanish"))
    if vanish is not None and (vanish.get(qn("w:val")) or "1").lower() not in _OFF:
        return True
    size = properties.find(qn("w:sz"))
    raw_size = size.get(qn("w:val")) if size is not None else None
    if raw_size and raw_size.isdigit() and int(raw_size) / 2 < MIN_VISIBLE_SIZE:  # half-points
        return True
    color = properties.find(qn("w:color"))
    rgb = _hex_rgb(color.get(qn("w:val"))) if color is not None else None
    return rgb is not None and delta_e(rgb, _background(run)) < MAX_DELTA_E


def _own_text(paragraph: Any, hidden: list[str]) -> str:
    """Text of a paragraph's own runs, leaving out text boxes nested inside it.

    Text of hidden runs is not returned; it is appended (one string per paragraph) to ``hidden``.
    """
    parts: list[str] = []
    concealed: list[str] = []
    for node in paragraph.iter():
        if node.tag not in (qn("w:t"), qn("w:tab"), qn("w:br")):
            continue
        if _inside_textbox(node, paragraph):
            continue
        if _run_hidden(node.getparent()):
            if node.tag == qn("w:t"):
                concealed.append(node.text or "")
        elif node.tag == qn("w:t"):
            parts.append(node.text or "")
        elif node.tag == qn("w:tab"):
            parts.append(" ")
        else:
            parts.append("\n")
    if text := "".join(concealed).strip():
        hidden.append(text)
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


def _paragraph_lines(paragraph: Any, hidden: list[str]) -> list[str]:
    lines: list[str] = []
    text = _own_text(paragraph, hidden).strip()
    if text:
        lines.append(f"{BULLET} {text}" if _is_list(paragraph) else text)
    # Text boxes: each inner paragraph is a line. AlternateContent repeats the same box in
    # its Choice and Fallback, so identical neighbours are dropped.
    for inner in paragraph.iter(qn("w:txbxContent")):
        for box_paragraph in inner.iter(qn("w:p")):
            box_text = _own_text(box_paragraph, hidden).strip()
            if box_text and (not lines or lines[-1] != box_text):
                lines.append(box_text)
    return lines


def _table_lines(table: Any, hidden: list[str]) -> list[str]:
    lines: list[str] = []
    for row in table.iter(qn("w:tr")):
        cells: list[str] = []
        for cell in row.findall(qn("w:tc")):
            text = " ".join(t for p in cell.iter(qn("w:p")) if (t := _own_text(p, hidden).strip()))
            if text:
                cells.append(text)
        if cells:
            lines.append(" | ".join(cells))
    return lines


def _block_lines(container: Any, hidden: list[str]) -> list[str]:
    lines: list[str] = []
    for child in container:
        if child.tag == qn("w:p"):
            lines.extend(_paragraph_lines(child, hidden))
        elif child.tag == qn("w:tbl"):
            lines.extend(_table_lines(child, hidden))
    return lines


def parse_docx(data: bytes) -> ParsedDocument:
    document = Document(io.BytesIO(data))
    hidden: list[str] = []
    headers: list[str] = []
    footers: list[str] = []
    for section in document.sections:
        for header in (section.header, section.first_page_header, section.even_page_header):
            headers.extend(_block_lines(header._element, hidden))
        for footer in (section.footer, section.first_page_footer, section.even_page_footer):
            footers.extend(_block_lines(footer._element, hidden))
    body = _block_lines(document.element.body, hidden)
    lines: list[str] = []
    for line in [*headers, *body, *footers]:
        if not lines or lines[-1] != line or line.startswith(BULLET):
            lines.append(line)
    text = "\n".join(lines).strip()
    runs = [HiddenRun(page=1, text=t) for t in dict.fromkeys(hidden)]  # DOCX has no pages
    return ParsedDocument(
        visible_text=text, hidden_runs=runs, page_count=None, status=status_for(text)
    )
