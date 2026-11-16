"""Areas of work and the title words that go with each (feature 002i, research R5). Pure."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AreaEntry:
    """One area of work and the words that go with it."""

    name: str
    signals: tuple[str, ...]  # words in roles, titles and skills that suggest the person works here
    avoid_in_titles: tuple[str, ...]  # title words that mark a job as being in this area
    compatible: tuple[str, ...]  # areas that go with this one (their avoid words are not proposed)


WorkAreaTable = Mapping[str, AreaEntry]
