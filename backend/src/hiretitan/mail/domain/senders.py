"""Which senders count as job alerts (FR-009, FR-010). Pure.

Addresses are put into a Gmail search query, so they are held to a plain shape: letters, digits
and ``. _ % + -`` before the ``@``, a dotted host after it. Nothing with a meaning in the search
language (quotes, brackets, colons, spaces) gets through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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
        raise SenderError(f"{raw!r} is not a plain email address.")
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
