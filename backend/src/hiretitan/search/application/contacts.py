"""Contacts and company notes: what the use cases need from storage (feature 002b).

This task adds the store protocols only; the use cases (list, add, edit, delete, set note) come
in T014. Contacts and notes are the person's own data and are never sent to an AI (FR-022), so
nothing under ``search/workflow``, ``prompts`` or ``platform/llm`` may import this module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from hiretitan.search.domain.contacts import ContactFields


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

    async def list_for_company(self, company_id: UUID) -> list[StoredContact]: ...

    async def update(self, contact_id: UUID, fields: ContactFields) -> StoredContact: ...

    async def delete(self, contact_id: UUID) -> None: ...

    async def find_by_name_key(self, company_id: UUID, key: str) -> StoredContact | None: ...

    async def find_by_link_key(self, company_id: UUID, key: str | None) -> StoredContact | None: ...

    async def counts_by_company(self) -> dict[UUID, tuple[int, bool]]: ...


class NotesStore(Protocol):
    async def get(self, company_id: UUID) -> StoredNote | None: ...

    async def set(self, company_id: UUID, body: str | None, *, source: str) -> None: ...
