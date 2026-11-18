"""What the drafts module needs from the rest of the app, as ports.

``hiretitan/drafts_wiring.py`` implements them with the profile and search modules, so ``drafts``
imports no other feature module (import-linter contract ``drafts-boundary``). Contacts reach the
workflow only as a recipient snapshot stored on the draft row, never as an input to a prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from hiretitan.drafts.domain.profile_view import ProfileView


@dataclass(frozen=True, slots=True)
class ConfirmedProfile:
    version_id: UUID | None
    view: ProfileView


@dataclass(frozen=True, slots=True)
class JobInfo:
    id: UUID
    title: str
    company_name: str
    company_id: UUID | None
    description: str
    state: str


@dataclass(frozen=True, slots=True)
class ContactInfo:
    id: UUID
    company_id: UUID
    name: str
    role: str | None


class ProfileFactsSource(Protocol):
    async def current(self) -> ConfirmedProfile | None: ...


class JobSource(Protocol):
    async def get(self, job_id: UUID) -> JobInfo | None:
        """The job, or None when it is unknown or deleted."""
        ...


class ContactLookup(Protocol):
    async def for_company(self, company_id: UUID) -> list[ContactInfo]: ...

    async def get(self, contact_id: UUID) -> ContactInfo | None: ...
