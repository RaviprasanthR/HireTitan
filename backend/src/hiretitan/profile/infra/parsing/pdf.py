"""Read the visible text of a PDF (FR-004, FR-005, FR-008, research R8).

Only characters a human can see are returned; hidden runs are reported separately and never
enter the AI input. Bullet glyphs stay as line starts: when a font has no Unicode map,
pdfplumber returns ``(cid:N)`` for the bullet, which is read as a bullet here.
"""

from __future__ import annotations

import io
import re
from typing import Final

import pdfplumber

from hiretitan.platform.untrusted.hidden_text import detect_hidden, visible_text
from hiretitan.profile.infra.parsing.types import ParsedDocument, status_for

BULLET: Final = "•"
_LEADING_BULLET: Final = re.compile(r"^\s*(?:(?:\(cid:\d+\)|[•▪●◦‣])\s*|[*–-]\s+)(?=\S)")  # noqa: RUF001 - the en dash is a bullet glyph


def _normalize_bullets(text: str) -> str:
    lines: list[str] = []
    for line in text.split("\n"):
        # A lone "-" or "*" followed by text is a bullet; "(cid:N)" is an unmapped glyph.
        match = _LEADING_BULLET.match(line)
        lines.append(f"{BULLET} {line[match.end() :]}" if match else line)
    return "\n".join(lines)


def parse_pdf(data: bytes) -> ParsedDocument:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        found = detect_hidden(pdf)
    text = _normalize_bullets(visible_text(found)).strip()
    return ParsedDocument(
        visible_text=text,
        hidden_runs=found.hidden_runs,
        page_count=found.page_count,
        status=status_for(text),
    )
