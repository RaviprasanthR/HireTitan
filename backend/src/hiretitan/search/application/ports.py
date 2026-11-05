"""Ports the search application depends on (constitution VI: external tools sit behind a port).

``CareerOpsPort`` reads company job boards through the bundled career-ops scanner. One company
failing never fails the others: every board gets its own ``ScanOk`` or ``ScanError``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BoardRef:
    """One company's job board: which provider and which board on it."""

    company_id: UUID
    vendor: str
    board_id: str


@dataclass(frozen=True, slots=True)
class Posting:
    """A job as the board lists it. Nothing here is cleaned or trusted yet."""

    title: str
    url: str
    location: str | None = None
    posted_at: datetime | None = None
    description: str | None = None
    requisition_id: str | None = None


@dataclass(frozen=True, slots=True)
class ScanOk:
    postings: list[Posting] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ScanError:
    message: str


CompanyScan = ScanOk | ScanError
ScanResult = dict[UUID, CompanyScan]


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """A board found behind a careers page address."""

    vendor: str
    board_id: str


class CareerOpsPort(Protocol):
    async def scan(self, refs: list[BoardRef]) -> ScanResult:
        """Read the given boards. The result has an entry for every company in ``refs``."""
        ...

    async def discover(self, careers_url: str) -> DiscoveryResult | None:
        """Work out which provider board sits behind a careers page, if it is one we can read."""
        ...
