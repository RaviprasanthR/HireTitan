"""002m T005: card and change rules (research R6, R7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hiretitan.assistant.domain.kinds import (
    IllegalCardMoveError,
    card_is_open,
    move_card,
    undo_refusal,
)

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)


def test_R7_card_transitions() -> None:
    assert move_card("proposed", "applying") == "applying"
    assert move_card("proposed", "cancelled") == "cancelled"
    assert move_card("proposed", "expired") == "expired"
    assert move_card("applying", "applied") == "applied"
    assert move_card("applying", "failed") == "failed"
    for current, target in (
        ("applied", "applying"),
        ("cancelled", "applying"),
        ("expired", "applying"),
        ("proposed", "applied"),  # never skips applying
        ("failed", "proposed"),
    ):
        with pytest.raises(IllegalCardMoveError):
            move_card(current, target)


def test_R7_card_open_only_while_proposed_and_not_expired() -> None:
    later = NOW + timedelta(minutes=30)
    assert card_is_open("proposed", later, NOW) is True
    assert card_is_open("proposed", later, later) is False
    assert card_is_open("applied", later, NOW) is False


def test_R6_change_transitions() -> None:
    ok = {
        "undone_at": None,
        "undoable_until": NOW + timedelta(hours=24),
        "is_latest": True,
        "current": {"state": "applied"},
        "after": {"state": "applied"},
        "now": NOW,
    }
    assert undo_refusal(**ok) is None  # type: ignore[arg-type]
    assert undo_refusal(**{**ok, "undone_at": NOW}) == "already_undone"  # type: ignore[arg-type]
    assert undo_refusal(**{**ok, "undoable_until": None}) == "not_undoable"  # type: ignore[arg-type]
    assert (
        undo_refusal(**{**ok, "now": NOW + timedelta(hours=24)}) == "too_late"  # type: ignore[arg-type]
    )
    assert undo_refusal(**{**ok, "is_latest": False}) == "not_latest"  # type: ignore[arg-type]
    assert (
        undo_refusal(**{**ok, "current": {"state": "inquired"}}) == "changed_since"  # type: ignore[arg-type]
    )
    assert undo_refusal(**{**ok, "current": None}) == "changed_since"  # type: ignore[arg-type]
