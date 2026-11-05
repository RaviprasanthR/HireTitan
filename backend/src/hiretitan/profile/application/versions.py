"""Reading the confirmed profile (FR-022) and deciding who created a version (FR-019/020)."""

from __future__ import annotations

from typing import Literal, Protocol

from hiretitan.profile.domain.content import ProfileContent

ManualCreator = Literal["manual", "manual_edit"]


class CurrentProfileReader(Protocol):
    async def current_content(self) -> ProfileContent | None: ...


async def get_current_profile(reader: CurrentProfileReader) -> ProfileContent | None:
    """The user's confirmed profile, or None until the first version exists.

    This is what other features read. It never exposes a review in progress or a draft.
    """
    return await reader.current_content()


def manual_creator(has_current_version: bool) -> ManualCreator:
    """A first profile typed in by hand is ``manual``; later edits are ``manual_edit``."""
    return "manual_edit" if has_current_version else "manual"
