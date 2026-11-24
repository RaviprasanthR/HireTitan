"""Card and change rules (002m research R6, R7). Pure: no framework, no database."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final, Literal

CardState = Literal["proposed", "applying", "applied", "cancelled", "expired", "failed"]
UndoRefusal = Literal["already_undone", "not_undoable", "too_late", "not_latest", "changed_since"]

_CARD_MOVES: Final[dict[str, frozenset[str]]] = {
    "proposed": frozenset({"applying", "cancelled", "expired"}),
    "applying": frozenset({"applied", "failed"}),
}


class IllegalCardMoveError(ValueError):
    pass


def move_card(current: str, target: str) -> str:
    """The card's next state; a card is applied only through ``applying`` and never reopens."""
    if target not in _CARD_MOVES.get(current, frozenset()):
        raise IllegalCardMoveError(f"A card cannot go from {current!r} to {target!r}")
    return target


def card_is_open(state: str, expires_at: datetime, now: datetime) -> bool:
    """Whether the person can still confirm or cancel the card."""
    return state == "proposed" and now < expires_at


def undo_refusal(
    *,
    undone_at: datetime | None,
    undoable_until: datetime | None,
    is_latest: bool,
    current: Mapping[str, Any] | None,
    after: Mapping[str, Any],
    now: datetime,
) -> UndoRefusal | None:
    """Why an Undo must be refused, or None when it may run (FR-014, EC-16).

    ``current`` is the target's touched fields as they are now (None when it is gone); an
    Undo never overwrites a change made since.
    """
    if undone_at is not None:
        return "already_undone"
    if undoable_until is None:
        return "not_undoable"
    if now >= undoable_until:
        return "too_late"
    if not is_latest:
        return "not_latest"
    if current is None or dict(current) != dict(after):
        return "changed_since"
    return None
