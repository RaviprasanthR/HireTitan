"""Reading, saving and suggesting preferences (public API of the preferences module).

Nothing here calls the AI or needs a profile, so it works with no key and no resume (FR-026).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from hiretitan.platform.clock import ClockPort
from hiretitan.preferences.domain.defaults import default_preferences
from hiretitan.preferences.domain.model import Preferences
from hiretitan.preferences.domain.rules import FieldError, save_errors
from hiretitan.profile.application.versions import CurrentProfileReader, get_current_profile

MAX_SKILL_SUGGESTIONS = 50


@dataclass(frozen=True, slots=True)
class StoredPreferences:
    content: Preferences
    saved_at: datetime | None  # None until the user first saves


@dataclass(frozen=True, slots=True)
class Suggestions:
    target_roles: tuple[str, ...]
    key_skills: tuple[str, ...]


class PreferencesStore(Protocol):
    async def read(self) -> StoredPreferences | None: ...

    async def write(self, prefs: Preferences, saved_at: datetime) -> None: ...


class PreferencesInvalid(Exception):
    """The preferences broke a save rule; ``errors`` names every field to mark."""

    def __init__(self, errors: list[FieldError]) -> None:
        super().__init__(f"{len(errors)} field(s) are not valid")
        self.errors = errors


async def get_preferences(store: PreferencesStore) -> StoredPreferences:
    """What the user saved, or the documented defaults when nothing was saved yet."""
    return await store.read() or StoredPreferences(default_preferences(), None)


async def save_preferences(
    store: PreferencesStore, clock: ClockPort, prefs: Preferences
) -> datetime:
    errors = save_errors(prefs)
    if errors:
        raise PreferencesInvalid(errors)
    saved_at = clock.now()
    await store.write(prefs, saved_at)
    return saved_at


async def get_default_country(store: PreferencesStore) -> str:
    """ISO country used to read phone numbers written without a country code (FR-008a)."""
    return (await get_preferences(store)).content.default_country


def _key(text: str) -> str:
    return " ".join(text.split()).casefold()


def _recency(job: Any) -> tuple[bool, tuple[int, int]]:
    """Current jobs first, then the latest end (or start) date."""
    when = job.end or job.start
    return (bool(job.current), (0, 0) if when is None else (when.year, when.month or 0))


async def get_suggestions(store: PreferencesStore, profile: CurrentProfileReader) -> Suggestions:
    """Ideas from the confirmed profile; the user adds them by clicking, never automatically."""
    content = await get_current_profile(profile)
    if content is None:
        return Suggestions((), ())
    chosen = (await get_preferences(store)).content

    roles: tuple[str, ...] = ()
    titles = [job for job in content.experience if job.title.strip()]
    if titles:
        title = max(titles, key=_recency).title
        if _key(title) not in {_key(r) for r in chosen.target_roles}:
            roles = (title,)

    taken = {_key(s) for s in chosen.key_skills}
    skills: list[str] = []
    for skill in content.skills:
        if _key(skill) not in taken:
            taken.add(_key(skill))
            skills.append(skill)
    return Suggestions(roles, tuple(skills[:MAX_SKILL_SUGGESTIONS]))
