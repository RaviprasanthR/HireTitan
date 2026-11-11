"""Matching a sheet row to a company already on the list (feature 002b, FR-003; research R4).

Pure. The website is compared first: the host must be equal once ``www.`` is dropped, so
``careers.acme.com`` is not ``acme.com``. The name is compared with case, spacing, punctuation,
accents and common company suffixes ignored. A row that fits one company is matched. Two
companies (a website match and a name match that point at different ones, or two name matches)
make the row ambiguous, and the importer skips it with both names. If a website match and a name
match agree on a company, that company wins even when the name also fits others.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit
from uuid import UUID

SUFFIXES: Final = frozenset({"inc", "ltd", "pvt", "llc", "technologies"})
_NON_WORD: Final = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class CompanyRef:
    id: UUID
    name: str
    website: str | None


@dataclass(frozen=True, slots=True)
class Matched:
    company_id: UUID


@dataclass(frozen=True, slots=True)
class NoMatch:
    pass


@dataclass(frozen=True, slots=True)
class Ambiguous:
    names: tuple[str, ...]


MatchResult = Matched | NoMatch | Ambiguous


def website_key(url: str | None) -> str | None:
    """The host without ``www.`` in lower case, or ``None`` if there is no usable host."""
    text = (url or "").strip()
    if not text or any(ch.isspace() for ch in text):
        return None
    parts = urlsplit(text if "://" in text else f"//{text}")
    host = (parts.hostname or "").removeprefix("www.")
    return host if "." in host else None


def name_match_key(name: str) -> str:
    """Lower-case letters and digits only, with trailing company suffixes (Inc, Ltd ...) dropped."""
    plain = "".join(
        ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch)
    )
    tokens = _NON_WORD.sub(" ", plain.lower()).split()
    while len(tokens) > 1 and tokens[-1] in SUFFIXES:
        tokens.pop()
    return "".join(tokens)


def match(name: str, website: str | None, companies: Iterable[CompanyRef]) -> MatchResult:
    refs = list(companies)
    wanted_site = website_key(website)
    wanted_name = name_match_key(name)
    by_site = {
        c.id for c in refs if wanted_site is not None and website_key(c.website) == wanted_site
    }
    by_name = {c.id for c in refs if wanted_name and name_match_key(c.name) == wanted_name}

    candidates = (by_site & by_name) or (by_site | by_name)
    if not candidates:
        return NoMatch()
    if len(candidates) == 1:
        return Matched(next(iter(candidates)))
    names = sorted(c.name for c in refs if c.id in candidates)
    return Ambiguous(tuple(names))
