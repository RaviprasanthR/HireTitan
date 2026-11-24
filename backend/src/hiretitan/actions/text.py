"""Bounded, screened text for the model (002m research R4, constitution III).

Titles, company names and short reasons come from outside the app (postings, alerts, pages).
They reach the model only sanitized, capped and screened; a value that looks like instructions
is replaced by a fixed marker, and the caller marks the item as flagged so the person sees it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.platform.untrusted.screen import screen

MASKED: Final = "[hidden: looks like instructions]"
SHORT: Final = 200
_SEVERE: Final = frozenset({"high", "medium"})


@dataclass(frozen=True, slots=True)
class Bounded:
    text: str
    flagged: bool = False


def bounded(value: str | None, cap: int = SHORT) -> Bounded:
    """One line of at most ``cap`` characters, or the marker when it looks like instructions."""
    if not value:
        return Bounded("")
    clean = " ".join(sanitize(value).text.split())
    if any(flag.severity in _SEVERE for flag in screen(clean)):
        return Bounded(MASKED, flagged=True)
    return Bounded(clean[:cap])


def screened(value: Any, cap: int = 400) -> tuple[Any, bool]:
    """A plain JSON-ready copy of ``value`` with every string bounded and screened.

    Dataclasses become dicts, dates ISO text, ids text. The flag is True when any string was
    masked, so the item can be marked for the person.
    """
    flagged = False

    def walk(item: Any) -> Any:
        nonlocal flagged
        if item is None or isinstance(item, bool | int | float):
            return item
        if isinstance(item, str):
            result = bounded(item, cap)
            flagged = flagged or result.flagged
            return result.text
        if isinstance(item, date | datetime):
            return item.isoformat()
        if isinstance(item, UUID | Decimal):
            return str(item)
        if is_dataclass(item) and not isinstance(item, type):
            return {f.name: walk(getattr(item, f.name)) for f in fields(item)}
        if isinstance(item, Mapping):
            return {str(k): walk(v) for k, v in item.items()}
        if isinstance(item, list | tuple | set | frozenset):
            return [walk(v) for v in item]
        return walk(str(item))

    return walk(value), flagged
