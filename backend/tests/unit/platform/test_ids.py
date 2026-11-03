"""T009: uuid7 stays strictly increasing when the clock stalls or steps back."""

from __future__ import annotations

import pytest

from hiretitan.platform.db import ids


def test_uuid7_increasing_when_clock_is_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ids.time, "time_ns", lambda: 1_800_000_000_000_000_000)
    generated = [ids.uuid7() for _ in range(5000)]  # > 4096: counter must roll over
    assert generated == sorted(generated)
    assert len(set(generated)) == len(generated)


def test_uuid7_increasing_when_clock_steps_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ids.time, "time_ns", lambda: 1_900_000_000_000_000_000)
    first = ids.uuid7()
    monkeypatch.setattr(ids.time, "time_ns", lambda: 1_899_999_999_000_000_000)
    assert ids.uuid7() > first
