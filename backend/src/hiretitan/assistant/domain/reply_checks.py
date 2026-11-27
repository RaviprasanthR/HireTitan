"""Checks on Mikasa's reply before it is shown and stored (002m research R9).

The model writes items as ref tokens (``[[job:<uuid>]]``) and in-app links as
``[[page:/path]]``. A ref the conversation never received from an action, or a link to a page
that does not exist, is removed: the panel must never show something the data did not give.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Final

MIKASA_TEXT_MAX: Final = 4000

_REF = re.compile(r"\[\[([a-z_]+:[0-9a-fA-F-]{36})\]\]")
_PAGE = re.compile(r"\[\[page:(/[^\]\s]*)\]\]")
_SPACES = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([.,;:!?])")


@dataclass(frozen=True, slots=True)
class ReplyCheck:
    text: str
    refs: list[str] = field(default_factory=list)  # refs kept, in order of appearance
    removed_refs: list[str] = field(default_factory=list)
    removed_links: list[str] = field(default_factory=list)
    truncated: bool = False


def _route_matches(path: str, route: str) -> bool:
    wanted = [part for part in route.split("/") if part]
    given = [part for part in path.split("?")[0].split("#")[0].split("/") if part]
    if len(wanted) != len(given):
        return False
    return all(w.startswith(":") or w == g for w, g in zip(wanted, given, strict=True))


def check_reply(text: str, *, known_refs: Collection[str], routes: Sequence[str]) -> ReplyCheck:
    kept: list[str] = []
    removed_refs: list[str] = []
    removed_links: list[str] = []

    def ref(match: re.Match[str]) -> str:
        value = match.group(1)
        if value in known_refs:
            if value not in kept:
                kept.append(value)
            return match.group(0)
        removed_refs.append(value)
        return ""

    def page(match: re.Match[str]) -> str:
        path = match.group(1)
        if any(_route_matches(path, route) for route in routes):
            return match.group(0)
        removed_links.append(path)
        return ""

    cleaned = _PAGE.sub(page, _REF.sub(ref, text))
    if removed_refs or removed_links:
        cleaned = _SPACE_BEFORE_PUNCT.sub(r"\1", _SPACES.sub(" ", cleaned))
    truncated = len(cleaned) > MIKASA_TEXT_MAX
    if truncated:
        cleaned = cleaned[:MIKASA_TEXT_MAX]
    return ReplyCheck(cleaned, kept, removed_refs, removed_links, truncated)
