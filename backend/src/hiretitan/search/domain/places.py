"""Place names a posting may use, mapped to one spelling (alias-aware matching, pure).

Only well-known alternative names are listed. A place that is not here is left unknown, never
guessed (FR-027).
"""

from __future__ import annotations

import re
from typing import Final

_SPLIT = re.compile(r"[^a-z0-9]+")

CITY_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "Bengaluru": ("bangalore", "bengaluru", "bengalooru"),
    "Gurugram": ("gurgaon", "gurugram"),
    "Mumbai": ("bombay", "mumbai", "navi mumbai"),
    "Chennai": ("madras", "chennai"),
    "Kolkata": ("calcutta", "kolkata"),
    "Pune": ("pune", "poona"),
    "Hyderabad": ("hyderabad", "secunderabad"),
    "Delhi": ("delhi", "new delhi"),
    "Noida": ("noida", "greater noida"),
    "Ahmedabad": ("ahmedabad",),
    "Kochi": ("kochi", "cochin"),
    "Thiruvananthapuram": ("trivandrum", "thiruvananthapuram"),
    "Coimbatore": ("coimbatore",),
    "Jaipur": ("jaipur",),
    "London": ("london",),
    "New York": ("new york", "new york city", "nyc"),
    "San Francisco": ("san francisco", "sf"),
    "Singapore": ("singapore",),
    "Dublin": ("dublin",),
    "Berlin": ("berlin",),
    "Toronto": ("toronto",),
    "Sydney": ("sydney",),
}

COUNTRY_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "IN": ("india", "in", "ind"),
    "US": ("united states", "united states of america", "usa", "us", "u s"),
    "GB": ("united kingdom", "uk", "great britain", "england", "gb"),
    "CA": ("canada", "ca"),
    "AU": ("australia", "au"),
    "DE": ("germany", "deutschland", "de"),
    "IE": ("ireland", "ie"),
    "SG": ("singapore", "sg"),
    "AE": ("united arab emirates", "uae", "ae"),
    "NL": ("netherlands", "nl"),
    "FR": ("france", "fr"),
}

_INDIAN_CITIES = (
    "Bengaluru",
    "Gurugram",
    "Mumbai",
    "Chennai",
    "Kolkata",
    "Pune",
    "Hyderabad",
    "Delhi",
    "Noida",
    "Ahmedabad",
    "Kochi",
    "Thiruvananthapuram",
    "Coimbatore",
    "Jaipur",
)
# a city that is only found in one country
CITY_COUNTRY: Final[dict[str, str]] = {
    **dict.fromkeys(_INDIAN_CITIES, "IN"),
    "London": "GB",
    "Dublin": "IE",
    "Berlin": "DE",
    "Singapore": "SG",
}


def key(text: str) -> str:
    """Lower-case words joined by single spaces."""
    return " ".join(part for part in _SPLIT.split(text.lower()) if part)


_CITY_BY_ALIAS: Final = {key(a): city for city, aliases in CITY_ALIASES.items() for a in aliases}
_COUNTRY_BY_ALIAS: Final = {
    key(a): code for code, aliases in COUNTRY_ALIASES.items() for a in aliases
}


def canonical_city(text: str | None) -> str | None:
    return _CITY_BY_ALIAS.get(key(text)) if text else None


def canonical_country(text: str | None) -> str | None:
    """ISO code for a country name or code; an unknown name gives None."""
    if not text:
        return None
    return _COUNTRY_BY_ALIAS.get(key(text))


def same_city(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return (canonical_city(a) or key(a)) == (canonical_city(b) or key(b))


def city_aliases(city: str) -> frozenset[str]:
    """Every spelling of this city (lower-case words), or just its own when it is not listed."""
    canonical = canonical_city(city)
    if canonical is None:
        return frozenset({key(city)})
    return frozenset(key(a) for a in CITY_ALIASES[canonical])
