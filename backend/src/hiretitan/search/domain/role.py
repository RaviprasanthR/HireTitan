"""A short role for a posting title, by rules only (used until the AI has given one).

"Senior Backend Engineer (Python) - Remote - Pune | Req 48213" becomes "Senior Backend Engineer".
Pure and deterministic: it only removes words, so it never adds anything the title lacks.
"""

from __future__ import annotations

import re
from typing import Final

ROLE_MAX: Final = 60

_EDGE: Final = "-" + chr(0x2013) + chr(0x2014) + "|/@:"
_BRACKETS: Final = re.compile(r"\([^)]*\)|\[[^\]]*\]|\{[^}]*\}")
_SEPARATORS: Final = re.compile(r"\s+[-\u2013\u2014|/@:]+\s+|\s*\|\s*|\s*[\u2013\u2014]\s*")
_REQ: Final = re.compile(r"\b(?:req(?:uisition)?|job|id|ref)\b[\s#:.-]*[\w-]*\d[\w-]*", re.I)
_HASH_ID: Final = re.compile(r"#\s*[\w-]*\d[\w-]*")


def short_role(title: str) -> str:
    text = _BRACKETS.sub(" ", title)
    text = _REQ.sub(" ", text)
    text = _HASH_ID.sub(" ", text)
    text = text.strip()
    first = "" if text[:1] in _EDGE else _SEPARATORS.split(text)[0]
    cleaned = " ".join(first.split()).strip(_EDGE + " ,;")
    if not cleaned:
        cleaned = " ".join(title.split())
    if len(cleaned) > ROLE_MAX:
        cut = cleaned[: ROLE_MAX - 1].rsplit(" ", 1)[0].rstrip(" ,;-")
        cleaned = (cut or cleaned[: ROLE_MAX - 1]) + "…"
    return cleaned
