"""Role synonyms: "backend engineer" also means "backend developer" (research R9).

Pure. The table maps a role phrase to its synonyms; a role matches whether the person typed the
phrase itself or one of its synonyms. Phrases are compared lower-case with punctuation and spacing
ignored, so "Backend-Engineer" and "backend   engineer" are the same role.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

SYNONYMS_PER_ROLE_MAX: Final = 20

_SEPARATORS = re.compile(r"[^a-z0-9+#]+")


def normalize_phrase(text: str) -> str:
    """Lower-case; each run of other characters becomes one space (``+`` and ``#`` stay)."""
    return _SEPARATORS.sub(" ", text.lower()).strip()


def expand(role: str, table: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    """The role first, then its known synonyms, without repeats. An unknown role is itself."""
    wanted = normalize_phrase(role)
    for key, synonyms in table.items():
        group = (normalize_phrase(key), *(normalize_phrase(s) for s in synonyms))
        if wanted in group:
            return (wanted, *dict.fromkeys(g for g in group if g != wanted))
    return (wanted,)
