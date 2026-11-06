"""Ports the search application depends on (constitution VI: external tools sit behind a port).

``CareerOpsPort`` reads company job boards through the bundled career-ops scanner. One company
failing never fails the others: every board gets its own ``ScanOk`` or ``ScanError``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from hiretitan.search.domain.proposer import ProposalInput


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


class StoredCompany(Protocol):
    """A company row as the seed loader needs to see it."""

    id: UUID
    origin: str
    user_modified: bool
    hidden: bool
    deleted_at: datetime | None


class CompanyStore(Protocol):
    """Where the seed loader reads and writes companies (implemented by the infra layer)."""

    async def get_by_key(self, key: str) -> StoredCompany | None: ...

    async def add(self, **fields: Any) -> StoredCompany: ...

    async def set_fields(self, company_id: UUID, **fields: Any) -> None: ...


class StoredRuleSet(Protocol):
    """A rule set row: ``rules`` and ``based_on`` are the JSON the domain serializes."""

    id: UUID
    version: int
    status: str  # proposed | approved | superseded
    rules: dict[str, Any]
    based_on: dict[str, Any]
    approved_at: datetime | None


class RuleSetStore(Protocol):
    async def approved(self) -> StoredRuleSet | None: ...

    async def proposed(self) -> StoredRuleSet | None: ...

    async def propose(self, rules: dict[str, Any], based_on: dict[str, Any]) -> StoredRuleSet: ...

    async def update_proposed(self, rules: dict[str, Any]) -> StoredRuleSet | None: ...

    async def approve(self, rule_set_id: UUID) -> StoredRuleSet: ...

    async def discard_proposed(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ProposalFacts:
    """What a proposal is built from, and the versions it was built on (FR-006)."""

    source: ProposalInput
    profile_version_id: UUID
    preferences_saved_at: datetime


class ProposalSource(Protocol):
    """Reads the confirmed profile and the saved preferences (composition adapter).

    Raises ``RulesUnavailableError`` when either is missing.
    """

    async def read(self) -> ProposalFacts: ...
