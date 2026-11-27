"""002m T005: target fingerprints for confirm cards (research R7, EC-02)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from hiretitan.assistant.domain.fingerprints import fingerprint, stale_targets


def test_EC02_fingerprint_changes_with_field() -> None:
    base = {"state": "explore", "title": "Backend Engineer"}
    assert fingerprint(base) == fingerprint({"title": "Backend Engineer", "state": "explore"})
    assert fingerprint(base) != fingerprint({**base, "state": "applied"})
    assert len(fingerprint(base)) == 64


def test_EC02_fingerprint_handles_dates_and_ids() -> None:
    value = {"at": datetime(2026, 11, 24, tzinfo=UTC), "id": UUID(int=7), "n": None}
    assert fingerprint(value) == fingerprint(dict(value))


def test_EC02_stale_targets_lists_changed_and_missing() -> None:
    saved = {"job:1": "a", "job:2": "b", "job:3": "c"}
    current = {"job:1": "a", "job:2": "changed"}  # job:3 was deleted
    assert stale_targets(saved, current) == ["job:2", "job:3"]
    assert stale_targets(saved, dict(saved)) == []
