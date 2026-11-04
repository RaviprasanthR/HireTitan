"""Sanitize untrusted text (constitution III, FR-006): the first step of the input pipeline.

NFKC-normalizes, removes control, zero-width and bidi characters, collapses whitespace while
keeping line breaks, and caps the length for the AI. When it cuts, it says where (offset and
the section heading the cut falls in) so the review screen can tell the user.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

MAX_CHARS: Final = 30_000

# Cf (format) covers zero-width, bidi and soft-hyphen characters; Cc covers controls. Newlines
# and tabs are handled before this runs.
_REMOVED_CATEGORIES: Final = frozenset({"Cc", "Cf"})
_HORIZONTAL: Final = re.compile(r"[ \t\f\v]+")
_BLANK_RUNS: Final = re.compile(r"\n{3,}")
_HEADING_WORDS: Final = re.compile(
    r"^(?:(?:work|professional|relevant)\s+)?"
    r"(?:experience|employment|education|skills?|technical skills|projects?|certifications?|"
    r"summary|profile|objective|achievements|awards|publications|languages|interests|"
    r"contact|references)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Truncation:
    offset: int  # number of characters kept
    heading: str | None  # the section heading the cut falls in, if one could be found


@dataclass(frozen=True, slots=True)
class Sanitized:
    text: str
    truncated: Truncation | None = None


def _strip_invisible(text: str) -> str:
    return "".join(
        ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in _REMOVED_CATEGORIES
    )


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 40:
        return False
    if _HEADING_WORDS.match(stripped):
        return True
    return stripped.isupper() and any(ch.isalpha() for ch in stripped)


def _heading_before(text: str, offset: int) -> str | None:
    for line in reversed(text[:offset].split("\n")):
        if _is_heading(line):
            return line.strip()
    return None


def sanitize(raw: str) -> Sanitized:
    text = unicodedata.normalize("NFKC", raw).replace("\r\n", "\n").replace("\r", "\n")
    text = _strip_invisible(text)
    lines = [_HORIZONTAL.sub(" ", line).strip() for line in text.split("\n")]
    text = _BLANK_RUNS.sub("\n\n", "\n".join(lines)).strip()
    if len(text) <= MAX_CHARS:
        return Sanitized(text)
    return Sanitized(text[:MAX_CHARS], Truncation(MAX_CHARS, _heading_before(text, MAX_CHARS)))
