"""Contacts and company-note endpoints (contracts/rest-api.md, "Contacts and notes").

The person's own details about people at companies. Nothing here fetches a link, sends anything
to an email, phone or LinkedIn, or hands data to an AI step (FR-015, FR-022).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.web.problems import ProblemError, problem
from hiretitan.search.application.companies import CompanyNotFoundError
from hiretitan.search.application.contacts import (
    ContactError,
    ContactExistsError,
    ContactNotFoundError,
    ContactView,
    NoteView,
    add_contact,
    delete_contact,
    edit_contact,
    list_contacts,
    set_note,
)
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, NotesRepo


@dataclass(frozen=True)
class SearchContactsApiDeps:
    sessions: async_sessionmaker[AsyncSession]


class ContactOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    role: str | None
    linkedin_url: str | None
    email: str | None
    phone: str | None
    confidence: Literal["high", "medium", "low"] | None
    note: str | None
    source: Literal["import", "typed"]
    updated_at: datetime


class NoteOut(BaseModel):
    body: str | None
    source: Literal["import", "typed"] | None
    updated_at: datetime | None


class ContactsOut(BaseModel):
    items: list[ContactOut]
    note: NoteOut | None


class ContactIn(BaseModel):
    # defaults, so a missing name is reported field by field like any other bad value
    name: str = ""
    role: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    confidence: str | None = None
    note: str | None = None


class ContactPatch(BaseModel):
    """Only the fields that are sent change; an empty text clears an optional field."""

    name: str | None = None
    role: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    confidence: str | None = None
    note: str | None = None


class NoteIn(BaseModel):
    body: str | None = None


def _contact_out(view: ContactView) -> ContactOut:
    return ContactOut.model_validate(asdict(view))


def _note_out(view: NoteView) -> NoteOut:
    return NoteOut.model_validate(asdict(view))


def _invalid(error: ContactError) -> Any:
    return problem(
        422,
        str(error),
        errors=[{"field": e.field, "message": e.message} for e in error.errors],
    )


def _no_company() -> ProblemError:
    return ProblemError(404, "That company does not exist.")


def _no_contact() -> ProblemError:
    return ProblemError(404, "That contact does not exist.")


DUPLICATE = "That name is already a contact at this company."


def _exists(error: ContactExistsError) -> ProblemError:
    return ProblemError(409, str(error), code="contact_exists")


def create_contacts_router(deps: SearchContactsApiDeps) -> APIRouter:
    router = APIRouter(prefix="/companies", tags=["contacts"])

    @router.get("/{company_id}/contacts", response_model=ContactsOut)
    async def contacts_of(company_id: UUID) -> ContactsOut:
        async with deps.sessions() as session:
            try:
                panel = await list_contacts(
                    CompaniesRepo(session), ContactsRepo(session), NotesRepo(session), company_id
                )
            except CompanyNotFoundError as error:
                raise _no_company() from error
        return ContactsOut(
            items=[_contact_out(c) for c in panel.items],
            note=_note_out(panel.note) if panel.note else None,
        )

    @router.post("/{company_id}/contacts", response_model=ContactOut, status_code=201)
    async def create_contact(company_id: UUID, body: ContactIn) -> Any:
        async with deps.sessions() as session:
            try:
                view = await add_contact(
                    CompaniesRepo(session), ContactsRepo(session), company_id, body.model_dump()
                )
                await session.commit()
            except CompanyNotFoundError as error:
                raise _no_company() from error
            except ContactError as error:
                return _invalid(error)
            except ContactExistsError as error:
                raise _exists(error) from error
            except IntegrityError as error:  # two requests with one name at the same moment
                raise _exists(ContactExistsError(DUPLICATE)) from error
        return _contact_out(view)

    @router.patch("/{company_id}/contacts/{contact_id}", response_model=ContactOut)
    async def change_contact(company_id: UUID, contact_id: UUID, body: ContactPatch) -> Any:
        async with deps.sessions() as session:
            try:
                view = await edit_contact(
                    CompaniesRepo(session),
                    ContactsRepo(session),
                    company_id,
                    contact_id,
                    body.model_dump(exclude_unset=True),
                )
                await session.commit()
            except CompanyNotFoundError as error:
                raise _no_company() from error
            except ContactNotFoundError as error:
                raise _no_contact() from error
            except ContactError as error:
                return _invalid(error)
            except ContactExistsError as error:
                raise _exists(error) from error
            except IntegrityError as error:  # two requests with one name at the same moment
                raise _exists(ContactExistsError(DUPLICATE)) from error
        return _contact_out(view)

    @router.delete("/{company_id}/contacts/{contact_id}", status_code=204)
    async def remove_contact(company_id: UUID, contact_id: UUID) -> Response:
        async with deps.sessions() as session:
            try:
                await delete_contact(
                    CompaniesRepo(session), ContactsRepo(session), company_id, contact_id
                )
                await session.commit()
            except CompanyNotFoundError as error:
                raise _no_company() from error
            except ContactNotFoundError as error:
                raise _no_contact() from error
        return Response(status_code=204)

    @router.put("/{company_id}/note", response_model=NoteOut)
    async def put_note(company_id: UUID, body: NoteIn) -> Any:
        async with deps.sessions() as session:
            try:
                view = await set_note(
                    CompaniesRepo(session), NotesRepo(session), company_id, body.body
                )
                await session.commit()
            except CompanyNotFoundError as error:
                raise _no_company() from error
            except ContactError as error:
                return _invalid(error)
        return _note_out(view)

    return router
