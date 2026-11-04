"""What a document parser returns (shared by the PDF and DOCX parsers)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

from hiretitan.platform.untrusted.hidden_text import HiddenRun

MIN_VISIBLE_CHARS: Final = 200

ParseStatus = Literal["parsed", "no_text"]


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    visible_text: str
    hidden_runs: list[HiddenRun] = field(default_factory=list)
    page_count: int | None = None
    status: ParseStatus = "parsed"


def status_for(visible_text: str) -> ParseStatus:
    """Fewer than 200 visible characters means no readable text (e.g. a scanned PDF)."""
    return "parsed" if len(visible_text.strip()) >= MIN_VISIBLE_CHARS else "no_text"
