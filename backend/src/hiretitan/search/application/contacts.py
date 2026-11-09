"""Contacts and company notes: what the use cases need from storage (feature 002b).

Contacts and notes are the person's own data and are never sent to an AI (FR-022), so
nothing under ``search/workflow``, ``prompts`` or ``platform/llm`` may import this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from hiretitan.search.application.companies import CompanyNotFoundError
from hiretitan.search.domain.contacts import (
    ContactFields,
    FieldIssue,
    check_company_note,
    check_contact,
    name_key,
)

CONTACT_FIELDS = ("name", "role", "linkedin_url", "email", "phone", "confidence", "note")


class StoredContact(Protocol):
    id: UUID
    company_id: UUID
    name: str
    name_key: str
    role: str | None
    linkedin_url: str | None
    link_key: str | None
    email: str | None
    phone: str | None
    confidence: str | None
    note: str | None
    source: str
    created_at: datetime
    updated_at: datetime


class StoredNote(Protocol):
    company_id: UUID
    body: str
    source: str
    updated_at: datetime


class ContactsStore(Protocol):
    async def add(
        self, company_id: UUID, fields: ContactFields, *, source: str
    ) -> StoredContact: ...

    async def get(self, contact_id: UUID) -> StoredContact | None: ...

    async def list_for_company(self, company_id: UUID) -> Sequence[StoredContact]: ...

    async def update(self, contact_id: UUID, fields: ContactFields) -> StoredContact: ...

    async def remove(self, contact_id: UUID) -> None: ...

    async def find_by_name_key(self, company_id: UUID, key: str) -> StoredContact | None: ...

    async def find_by_link_key(self, company_id: UUID, key: str | None) -> StoredContact | None: ...

    async def counts_by_company(self) -> dict[UUID, tuple[int, bool]]: ...


class NotesStore(Protocol):
    async def get(self, company_id: UUID) -> StoredNote | None: ...

    async def set(self, company_id: UUID, body: str | None, *, source: str) -> None: ...


class ContactError(ValueError):
    """A typed contact or note failed its checks; nothing was saved."""

    def __init__(self, errors: list[FieldIssue]) -> None:
        super().__init__(" ".join(e.message for e in errors))
        self.errors = errors


class ContactExistsError(ValueError):
    """The company already has a contact with that name."""


class ContactNotFoundError(LookupError):
    """There is no such contact on that company."""


class CompanyLookup(Protocol):
    async def get(self, company_id: UUID) -> Any: ...


@dataclass(frozen=True, slots=True)
class ContactView:
    id: UUID
    company_id: UUID
    name: str
    role: str | None
    linkedin_url: str | None
    email: str | None
    phone: str | None
    confidence: str | None
    note: str | None
    source: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class NoteView:
    body: str | None
    source: str | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ContactsPanel:
    items: list[ContactView]
    note: NoteView | None


def contact_view(row: StoredContact) -> ContactView:
    return ContactView(
        id=row.id,
        company_id=row.company_id,
        name=row.name,
        role=row.role,
        linkedin_url=row.linkedin_url,
        email=row.email,
        phone=row.phone,
        confidence=row.confidence,
        note=row.note,
        source=row.source,
        updated_at=row.updated_at,
    )


async def _company(companies: CompanyLookup, company_id: UUID) -> None:
    row = await companies.get(company_id)
    if row is None or row.deleted_at is not None:
        raise CompanyNotFoundError(str(company_id))


async def _contact(contacts: ContactsStore, company_id: UUID, contact_id: UUID) -> StoredContact:
    row = await contacts.get(contact_id)
    if row is None or row.company_id != company_id:
        raise ContactNotFoundError(str(contact_id))
    return row


def _only_contact_fields(data: dict[str, str | None]) -> dict[str, str | None]:
    return {k: v for k, v in data.items() if k in CONTACT_FIELDS}


async def list_contacts(
    companies: CompanyLookup, contacts: ContactsStore, notes: NotesStore, company_id: UUID
) -> ContactsPanel:
    """Everything the company panel shows, in one call."""
    await _company(companies, company_id)
    note = await notes.get(company_id)
    return ContactsPanel(
        items=[contact_view(c) for c in await contacts.list_for_company(company_id)],
        note=NoteView(note.body, note.source, note.updated_at) if note else None,
    )


async def add_contact(
    companies: CompanyLookup,
    contacts: ContactsStore,
    company_id: UUID,
    data: dict[str, str | None],
) -> ContactView:
    """A contact the person typed. Only the name is required (FR-009)."""
    await _company(companies, company_id)
    fields, issues = check_contact(**_only_contact_fields(data))
    if fields is None:
        raise ContactError(issues)
    if await contacts.find_by_name_key(company_id, name_key(fields.name)) is not None:
        raise ContactExistsError(f"{fields.name} is already a contact at this company.")
    return contact_view(await contacts.add(company_id, fields, source="typed"))


async def edit_contact(
    companies: CompanyLookup,
    contacts: ContactsStore,
    company_id: UUID,
    contact_id: UUID,
    changes: dict[str, str | None],
) -> ContactView:
    """Change the fields that were sent; an empty text clears an optional field."""
    await _company(companies, company_id)
    row = await _contact(contacts, company_id, contact_id)
    merged: dict[str, str | None] = {
        "name": row.name,
        "role": row.role,
        "linkedin_url": row.linkedin_url,
        "email": row.email,
        "phone": row.phone,
        "confidence": row.confidence,
        "note": row.note,
    }
    merged.update(_only_contact_fields(changes))
    fields, issues = check_contact(**merged)
    if fields is None:
        raise ContactError(issues)
    key = name_key(fields.name)
    if key != row.name_key:
        other = await contacts.find_by_name_key(company_id, key)
        if other is not None and other.id != row.id:
            raise ContactExistsError(f"{fields.name} is already a contact at this company.")
    return contact_view(await contacts.update(contact_id, fields))


async def delete_contact(
    companies: CompanyLookup, contacts: ContactsStore, company_id: UUID, contact_id: UUID
) -> None:
    await _company(companies, company_id)
    await _contact(contacts, company_id, contact_id)
    await contacts.remove(contact_id)


async def set_note(
    companies: CompanyLookup, notes: NotesStore, company_id: UUID, body: str | None
) -> NoteView:
    """Save the company note as typed; an empty or blank text removes it (FR-010)."""
    await _company(companies, company_id)
    text, issues = check_company_note(body)
    if issues:
        raise ContactError(issues)
    await notes.set(company_id, text, source="typed")
    saved = await notes.get(company_id)
    if saved is None:
        return NoteView(None, None, None)
    return NoteView(saved.body, saved.source, saved.updated_at)
