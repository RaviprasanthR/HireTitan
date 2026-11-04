"""First-run setup: the user's name and when setup was finished (FR-039, FR-040)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

MAX_NAME = 120


@dataclass(frozen=True, slots=True)
class OnboardingRecord:
    display_name: str | None
    setup_completed_at: datetime | None


class OnboardingStore(Protocol):
    async def read_onboarding(self) -> OnboardingRecord: ...

    async def write_display_name(self, name: str) -> None: ...

    async def write_setup_completed(self, at: datetime) -> None: ...


class SetupNotReady(Exception):
    """Setup cannot be finished before a profile is confirmed and preferences are saved."""


async def get_onboarding_record(store: OnboardingStore) -> OnboardingRecord:
    return await store.read_onboarding()


async def set_display_name(store: OnboardingStore, name: str) -> str:
    """Save the user's own name (never AI output). Raises ``ValueError`` if not 1-120 characters."""
    cleaned = " ".join(name.split())
    if not 1 <= len(cleaned) <= MAX_NAME:
        raise ValueError(f"The name must be 1 to {MAX_NAME} characters")
    await store.write_display_name(cleaned)
    return cleaned


async def complete_setup(
    store: OnboardingStore, now: datetime, *, profile_confirmed: bool, preferences_saved: bool
) -> datetime:
    """Record that setup is finished. A second call keeps the first time."""
    if not (profile_confirmed and preferences_saved):
        raise SetupNotReady("Confirm your profile and save your preferences first")
    record = await store.read_onboarding()
    if record.setup_completed_at is not None:
        return record.setup_completed_at
    await store.write_setup_completed(now)
    return now
