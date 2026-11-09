"""Turn a cleaned posting into job fields (pure).

The text arrives already sanitized. A fact the posting does not state stays ``None``; nothing is
guessed (FR-027).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from hiretitan.search.domain.places import CITY_COUNTRY, canonical_city, canonical_country, key

_TRACKING_PARAMS = frozenset(
    {
        "gclid",
        "fbclid",
        "gh_src",
        "ref",
        "source",
        "src",
        "trk",
        "trackingid",
        "lever-source",
        "lever-origin",
        "mc_cid",
        "mc_eid",
    }
)
_YEARS = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:\+|(?:-|2013|to)\s*\d{1,2})?\s*\+?\s*years?\b", re.I)
_PART_SPLIT = re.compile(r"[,/|;()]|\s+-\s+")
_WORK_MODES = (
    ("hybrid", re.compile(r"\bhybrid\b", re.I)),
    ("remote", re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b", re.I)),
    ("onsite", re.compile(r"\bon[\s-]?site\b|\bin[\s-]office\b", re.I)),
)


@dataclass(frozen=True, slots=True)
class NormalizedJob:
    title: str
    location_text: str | None
    city: str | None
    country: str | None
    work_mode: str | None
    posted_at: datetime | None
    skills_found: tuple[str, ...]
    years_found: Decimal | None
    canonical_url: str | None
    requisition_id: str | None


def canonical_url(url: str) -> str | None:
    """Lower-case scheme and host; no tracking parameters, fragment or trailing slash."""
    text = url.strip()
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc or " " in text:
        return None
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")
    )
    path = parts.path.rstrip("/") if len(parts.path) > 1 else parts.path
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def _place(location_text: str | None) -> tuple[str | None, str | None]:
    """City and country named in the text; two-letter codes count only as the last part."""
    if not location_text:
        return None, None
    parts = [p for p in _PART_SPLIT.split(location_text) if p.strip()]
    city = next((c for p in parts if (c := canonical_city(p))), None)
    country = next((c for p in parts if len(key(p)) > 3 and (c := canonical_country(p))), None)
    if country is None and parts:
        country = canonical_country(parts[-1]) if len(parts) > 1 else None
    if country is None and city is not None:
        country = CITY_COUNTRY.get(city)
    return city, country


def _work_mode(*texts: str | None) -> str | None:
    found = {
        mode for text in texts if text for mode, pattern in _WORK_MODES if pattern.search(text)
    }
    for mode, _ in _WORK_MODES:  # hybrid wins over remote, remote over onsite
        if mode in found:
            return mode
    return None


def _skills(stack_keywords: tuple[str, ...], *texts: str) -> tuple[str, ...]:
    haystack = " ".join(texts).lower()
    found: list[str] = []
    for keyword in stack_keywords:
        pattern = rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])"
        if keyword.strip() and keyword not in found and re.search(pattern, haystack):
            found.append(keyword)
    return tuple(found)


def _years(description: str) -> Decimal | None:
    match = _YEARS.search(description)
    return Decimal(match.group(1)) if match else None


def normalize_job(
    *,
    title: str,
    url: str,
    location_text: str | None,
    posted_at: datetime | None,
    description: str,
    requisition_id: str | None,
    stack_keywords: tuple[str, ...],
) -> NormalizedJob:
    location = location_text.strip() if location_text and location_text.strip() else None
    city, country = _place(location)
    return NormalizedJob(
        title=title.strip(),
        location_text=location,
        city=city,
        country=country,
        work_mode=_work_mode(location, title),
        posted_at=posted_at,
        skills_found=_skills(stack_keywords, title, description),
        years_found=_years(description),
        canonical_url=canonical_url(url),
        requisition_id=requisition_id,
    )
