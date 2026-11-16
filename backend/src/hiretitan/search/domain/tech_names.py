"""Programming languages and frameworks named in job titles (feature 002i, research R6). Pure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TechKind = Literal["language", "framework"]


@dataclass(frozen=True, slots=True)
class TechName:
    """One technology, how it may be written, and (for ordinary words like Go) where it counts."""

    name: str
    kind: TechKind
    aliases: tuple[str, ...]
    context: tuple[str, ...] = ()  # when set, the name counts only next to one of these words


TechTable = tuple[TechName, ...]
