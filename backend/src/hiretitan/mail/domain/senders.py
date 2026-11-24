"""Which senders count as job alerts (FR-009, FR-010). Pure.

Addresses are put into a Gmail search query, so they are held to a plain shape: letters, digits
and ``. _ % + -`` before the ``@``, a dotted host after it. Nothing with a meaning in the search
language (quotes, brackets, colons, spaces) gets through.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parseaddr
from typing import Any, Final

SITES: Final = ("linkedin", "naukri", "indeed", "foundit", "instahyre", "cutshort", "other")
ADDRESS_MAX: Final = 320
ADDRESS_MIN: Final = 3
# The first character is a letter, digit, dot, underscore or percent: a leading ``-`` negates the
# term in a Gmail search and ``+`` is no better, so neither may start an address.
_ADDRESS: Final = re.compile(r"^[a-z0-9._%][a-z0-9._%+\-]*@[a-z0-9\-]+(\.[a-z0-9\-]+)+$")


class SenderError(ValueError):
    """A sender address or the shipped list is not acceptable."""


@dataclass(frozen=True, slots=True)
class SeedSender:
    site: str
    address: str


def normalize_address(raw: str) -> str:
    """The address trimmed and lower-cased, or ``SenderError``."""
    address = raw.strip().lower()
    if not ADDRESS_MIN <= len(address) <= ADDRESS_MAX or not _ADDRESS.match(address):
        raise SenderError(f"{raw[:80]!r} is not a plain email address.")
    return address


def parse_seed(raw: Any) -> tuple[SeedSender, ...]:
    """The shipped list: ``senders`` maps a built-in site to its addresses."""
    senders = raw.get("senders") if isinstance(raw, dict) else None
    if not isinstance(senders, dict) or not senders:
        raise SenderError("The sender list must map each site to its addresses.")
    found: list[SeedSender] = []
    seen: set[str] = set()
    for site, addresses in senders.items():
        if site not in SITES or site == "other":
            raise SenderError(f"{site!r} is not a built-in site.")
        if not isinstance(addresses, list) or not addresses:
            raise SenderError(f"{site}: expected a list of addresses.")
        for item in addresses:
            if not isinstance(item, str):
                raise SenderError(f"{site}: every address must be text.")
            address = normalize_address(item)
            if address in seen:
                raise SenderError(f"{address} is listed twice.")
            seen.add(address)
            found.append(SeedSender(site, address))
    return tuple(found)


WINDOW: Final = timedelta(hours=24)  # every check reads the last 24 hours (FR-011)


def window_start(now: datetime) -> datetime:
    """The start of a check's reading window: 24 hours before it starts."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("A check's start needs a time zone.")
    return now - WINDOW


# The domain each built-in site sends its mail from. Mail from these domains is looked at as well
# as the listed addresses, because a site's alert address changes without notice; only emails in
# which a reader finds jobs are kept, the rest is dropped (2026-11-22, amends FR-009).
SITE_DOMAINS: Final[dict[str, tuple[str, ...]]] = {
    "linkedin": ("linkedin.com",),
    "naukri": ("naukri.com",),
    "indeed": ("indeed.com",),
    "foundit": ("foundit.in",),
    "instahyre": ("instahyre.com",),
    "cutshort": ("cutshort.io",),
}
_ALL_DOMAINS: Final = frozenset(d for domains in SITE_DOMAINS.values() for d in domains)


def domains_of(sites: Iterable[str]) -> list[str]:
    """The domains of the built-in sites among ``sites``, sorted."""
    return sorted({d for site in sites for d in SITE_DOMAINS.get(site, ())})


def site_for_address(address: str, sites: Iterable[str]) -> str | None:
    """The built-in site (among ``sites``) whose domain the address is at, or its sub-domain.

    ``noreply@mail.naukri.com`` belongs to Naukri; ``x@evilnaukri.com`` and
    ``x@naukri.com.evil.example`` do not. ``None`` for anything that is not a plain address."""
    try:
        clean = normalize_address(address)
    except SenderError:
        return None
    host = clean.rsplit("@", 1)[1]
    for site in sorted(set(sites)):
        for domain in SITE_DOMAINS.get(site, ()):
            if host == domain or host.endswith("." + domain):
                return site
    return None


def build_query(
    addresses: Sequence[str],
    now: datetime,
    domains: Sequence[str] = (),
    window: timedelta = WINDOW,
) -> str:
    """The Gmail search: ``from:(a OR b OR site.com) after:<epoch>`` and nothing else (FR-009).

    Built from the sender list and the built-in site domains only. Every address and domain is
    checked again here, so no text with a meaning in Gmail's search language can reach the query,
    however the list was filled. A domain must be one of the built-in sites'."""
    clean = sorted({normalize_address(address) for address in addresses})
    for domain in domains:
        if domain not in _ALL_DOMAINS:
            raise SenderError(f"{domain!r} is not a job site's domain.")
    parts = [*clean, *sorted(set(domains))]
    parts.sort(key=lambda p: ("@" not in p, p))  # addresses first, then domains
    if not parts:
        raise SenderError("There is no sender to look for.")
    # a check always reads 24 hours (FR-011); only the layout tool looks further back
    since = window_start(now) + WINDOW - window
    return f"from:({' OR '.join(parts)}) after:{int(since.timestamp())}"


_SENDER_QUERY: Final = re.compile(
    r"^from:\((?P<senders>[a-z0-9@._%+\-]+(?: OR [a-z0-9@._%+\-]+)*)\) after:\d{1,12}$"
)


def _valid_term(term: str) -> bool:
    if term in _ALL_DOMAINS:
        return True
    try:
        return normalize_address(term) == term
    except SenderError:
        return False


def is_sender_query(query: str) -> bool:
    """True only for what ``build_query`` makes: every term a valid address or a built-in site's
    domain, then a time, nothing else."""
    match = _SENDER_QUERY.match(query)
    if match is None:
        return False
    return all(_valid_term(term) for term in match.group("senders").split(" OR "))


def address_from_header(value: str) -> str:
    """The address in a ``From`` header, lower-cased, or ``""`` when it cannot be trusted.

    Gmail's ``from:`` search also matches display names, so anyone can send mail whose display
    name is a listed address. A display name that contains ``@`` is therefore never trusted, and an
    address that is not plain (control characters, spaces, absurd length) is not an address.
    """
    name, address = parseaddr(value)
    if "@" in name:
        return ""
    try:
        return normalize_address(address)
    except SenderError:
        return ""
