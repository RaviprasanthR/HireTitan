"""Mikasa's small changes to companies, contacts and notes (002m contracts/actions.md).

Contacts and notes are private (002b FR-022, research R5): their values come from the person's
message and are saved through the normal use cases, but what goes back to the model is only a
summary that names the company, and a ref. The change record keeps the values locally for Undo.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from hiretitan.actions.refs import Ref
from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, Applied, ChangeView
from hiretitan.actions.text import bounded
from hiretitan.search.application.companies import (
    CompanyError,
    CompanyNotFoundError,
    hide_company,
    update_company,
)
from hiretitan.search.application.contacts import (
    ContactError,
    ContactExistsError,
    ContactNotFoundError,
    add_contact,
    edit_contact,
    set_note,
)
from hiretitan.search.application.discovery import add_company
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.models import CompanyNoteRow, CompanyRow, ContactRow, JobRow
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, NotesRepo

NOT_FOUND = ActionError("not_found", "That company is not in HireTitan.")
COMPANY_FIELDS = ("name", "city", "website", "careers_url", "hidden", "user_modified")
CONTACT_FIELDS = ("name", "role", "linkedin_url", "email", "phone", "confidence", "note")


async def _company(ctx: ActionContext, company_id: UUID) -> CompanyRow | None:
    row = await ctx.session.get(CompanyRow, company_id, populate_existing=True)
    return None if row is None or row.deleted_at is not None else row


def _company_fields(row: CompanyRow) -> dict[str, Any]:
    return {name: getattr(row, name) for name in COMPANY_FIELDS}


# ---- add_company ---------------------------------------------------------------------------


class AddCompanyArgs(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    careers_url: str = Field(
        "", max_length=500, description="The careers page, if the person gave one"
    )
    city: str | None = Field(None, max_length=80)
    website: str | None = Field(None, max_length=500)


async def _added_company_fields(ctx: ActionContext, company_id: UUID) -> Mapping[str, Any] | None:
    row = await _company(ctx, company_id)
    if row is None:
        return None
    uses = [
        select(func.count()).select_from(JobRow).where(JobRow.company_id == company_id),
        select(func.count()).select_from(ContactRow).where(ContactRow.company_id == company_id),
        select(func.count())
        .select_from(CompanyNoteRow)
        .where(CompanyNoteRow.company_id == company_id),
    ]
    used = sum([await ctx.session.scalar(query) or 0 for query in uses])
    return {**_company_fields(row), "used": used}


async def add_company_action(ctx: ActionContext, args: AddCompanyArgs) -> Applied | ActionError:
    try:
        view = await add_company(
            CompaniesRepo(ctx.session),
            name=args.name,
            careers_url=args.careers_url,
            city=args.city,
            website=args.website,
        )
    except CompanyError as error:
        return ActionError("invalid", str(error))
    after = await _added_company_fields(ctx, view.id)
    assert after is not None
    ref = str(Ref("company", view.id))
    return Applied(
        "company",
        view.id,
        {},
        dict(after),
        f"Added {bounded(view.name).text} to your companies.",
        [ref],
        [ref],
    )


async def remove_added_company(ctx: ActionContext, change: ChangeView) -> None:
    """Undo of an add: gone for good; the change rules checked nothing uses it yet."""
    await ctx.session.execute(delete(CompanyRow).where(CompanyRow.id == change.target_id))


# ---- edit_company --------------------------------------------------------------------------


class EditCompanyArgs(BaseModel):
    company: str = Field(description="The company's ref, like company:<id>")
    name: str | None = Field(None, max_length=120)
    city: str | None = Field(None, max_length=80, description="An empty text clears it")
    website: str | None = Field(None, max_length=500, description="An empty text clears it")
    careers_url: str | None = Field(None, max_length=500, description="An empty text clears it")
    hidden: bool | None = Field(None, description="Hide it from searches, or show it again")


async def _edited_fields(ctx: ActionContext, company_id: UUID) -> Mapping[str, Any] | None:
    row = await _company(ctx, company_id)
    return None if row is None else _company_fields(row)


async def edit_company_action(ctx: ActionContext, args: EditCompanyArgs) -> Applied | ActionError:
    company_id = Ref.parse(args.company, expect="company").id
    row = await _company(ctx, company_id)
    if row is None:
        return NOT_FOUND
    before = _company_fields(row)
    sent = args.model_fields_set - {"company", "hidden"}
    changes = {name: getattr(args, name) for name in sent}
    if not changes and args.hidden is None:
        return ActionError("nothing_to_change", "Say what to change about the company.")
    repo = CompaniesRepo(ctx.session)
    try:
        if changes:
            await update_company(repo, company_id, changes)
        if args.hidden is not None:
            await hide_company(repo, company_id, hidden=args.hidden)
    except CompanyNotFoundError:
        return NOT_FOUND
    except CompanyError as error:
        return ActionError("invalid", str(error))
    after = await _edited_fields(ctx, company_id)
    assert after is not None
    what = "hidden" if args.hidden else "shown again" if args.hidden is False else "updated"
    return Applied(
        "company",
        company_id,
        before,
        dict(after),
        f"{bounded(str(after['name'])).text} {what}.",
        [str(Ref("company", company_id))],
    )


async def put_company_back(ctx: ActionContext, change: ChangeView) -> None:
    await CompaniesRepo(ctx.session).set_fields(change.target_id, **change.before)


# ---- contacts ------------------------------------------------------------------------------


class AddContactArgs(BaseModel):
    company: str = Field(description="The company's ref, like company:<id>")
    name: str = Field(min_length=1, max_length=120, description="As the person typed it")
    role: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=254)
    phone: str | None = Field(None, max_length=30)
    linkedin_url: str | None = Field(None, max_length=500)
    note: str | None = Field(None, max_length=2000)


class EditContactArgs(BaseModel):
    contact: str = Field(description="The contact's ref, like contact:<id>")
    name: str | None = Field(None, max_length=120)
    role: str | None = Field(None, max_length=120, description="An empty text clears it")
    email: str | None = Field(None, max_length=254, description="An empty text clears it")
    phone: str | None = Field(None, max_length=30, description="An empty text clears it")
    linkedin_url: str | None = Field(None, max_length=500, description="An empty text clears it")
    note: str | None = Field(None, max_length=2000, description="An empty text clears it")


def _contact_fields(row: ContactRow) -> dict[str, Any]:
    return {name: getattr(row, name) for name in CONTACT_FIELDS}


async def _contact_now(ctx: ActionContext, contact_id: UUID) -> Mapping[str, Any] | None:
    row = await ctx.session.get(ContactRow, contact_id, populate_existing=True)
    return None if row is None else _contact_fields(row)


async def add_contact_action(ctx: ActionContext, args: AddContactArgs) -> Applied | ActionError:
    company_id = Ref.parse(args.company, expect="company").id
    company = await _company(ctx, company_id)
    if company is None:
        return NOT_FOUND
    data = args.model_dump(exclude={"company"})
    try:
        view = await add_contact(
            CompaniesRepo(ctx.session), ContactsRepo(ctx.session), company_id, data
        )
    except (ContactError, ContactExistsError) as error:
        return ActionError("invalid", str(error))
    except CompanyNotFoundError:
        return NOT_FOUND
    after = await _contact_now(ctx, view.id)
    assert after is not None
    ref = str(Ref("contact", view.id))
    return Applied(
        "contact",
        view.id,
        {},
        dict(after),
        f"Added a contact at {bounded(company.name).text}.",  # never the contact's details
        [ref],
        [ref],
    )


async def remove_added_contact(ctx: ActionContext, change: ChangeView) -> None:
    await ContactsRepo(ctx.session).remove(change.target_id)


async def edit_contact_action(ctx: ActionContext, args: EditContactArgs) -> Applied | ActionError:
    contact_id = Ref.parse(args.contact, expect="contact").id
    row = await ctx.session.get(ContactRow, contact_id)
    if row is None:
        return ActionError("not_found", "That contact is not in HireTitan.")
    company = await _company(ctx, row.company_id)
    if company is None:
        return NOT_FOUND
    before = _contact_fields(row)
    changes = {name: getattr(args, name) for name in args.model_fields_set - {"contact"}}
    if not changes:
        return ActionError("nothing_to_change", "Say what to change about the contact.")
    try:
        await edit_contact(
            CompaniesRepo(ctx.session),
            ContactsRepo(ctx.session),
            row.company_id,
            contact_id,
            changes,
        )
    except (ContactError, ContactExistsError) as error:
        return ActionError("invalid", str(error))
    except (CompanyNotFoundError, ContactNotFoundError):
        return ActionError("not_found", "That contact is not in HireTitan.")
    after = await _contact_now(ctx, contact_id)
    assert after is not None
    return Applied(
        "contact",
        contact_id,
        before,
        dict(after),
        f"Updated a contact at {bounded(company.name).text}.",
        [str(Ref("contact", contact_id))],
    )


async def put_contact_back(ctx: ActionContext, change: ChangeView) -> None:
    await ContactsRepo(ctx.session).update(change.target_id, ContactFields(**change.before))


# ---- the company note ----------------------------------------------------------------------


class NoteArgs(BaseModel):
    company: str = Field(description="The company's ref, like company:<id>")
    text: str = Field(
        max_length=5000, description="The whole note as it should read; empty removes it"
    )


async def _note_now(ctx: ActionContext, company_id: UUID) -> Mapping[str, Any] | None:
    note = await NotesRepo(ctx.session).get(company_id)
    return {"body": note.body if note else None}


async def set_note_action(ctx: ActionContext, args: NoteArgs) -> Applied | ActionError:
    company_id = Ref.parse(args.company, expect="company").id
    company = await _company(ctx, company_id)
    if company is None:
        return NOT_FOUND
    before = await _note_now(ctx, company_id)
    assert before is not None
    try:
        await set_note(CompaniesRepo(ctx.session), NotesRepo(ctx.session), company_id, args.text)
    except ContactError as error:
        return ActionError("invalid", str(error))
    after = await _note_now(ctx, company_id)
    assert after is not None
    return Applied(
        "note",
        company_id,
        dict(before),
        dict(after),
        f"Saved your note on {bounded(company.name).text}.",
        [str(Ref("note", company_id))] if after["body"] else [],
    )


async def put_note_back(ctx: ActionContext, change: ChangeView) -> None:
    await NotesRepo(ctx.session).set(change.target_id, change.before["body"], source="typed")


INVALIDATE = ("companies", "contacts")

CHANGES: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="add_company",
        description="Add a company to the person's list. The careers page is optional.",
        args=AddCompanyArgs,
        kind="small",
        handler=add_company_action,
        undo=remove_added_company,
        current=_added_company_fields,
        invalidate=INVALIDATE,
        mirrors=("POST /companies",),
    ),
    ActionSpec(
        name="edit_company",
        description="Change one company's name, city, website or careers page, or hide or show it.",
        args=EditCompanyArgs,
        kind="small",
        handler=edit_company_action,
        undo=put_company_back,
        current=_edited_fields,
        invalidate=INVALIDATE,
        mirrors=("PATCH /companies/{company_id}",),
    ),
    ActionSpec(
        name="add_contact",
        description="Add a contact at a company with the details the person typed. You get a "
        "ref back, never the details.",
        args=AddContactArgs,
        kind="small",
        private=True,
        handler=add_contact_action,
        undo=remove_added_contact,
        current=_contact_now,
        invalidate=INVALIDATE,
        mirrors=("POST /companies/{company_id}/contacts",),
    ),
    ActionSpec(
        name="edit_contact",
        description="Change a contact's details with what the person typed (a contact ref).",
        args=EditContactArgs,
        kind="small",
        private=True,
        handler=edit_contact_action,
        undo=put_contact_back,
        current=_contact_now,
        invalidate=INVALIDATE,
        mirrors=("PATCH /companies/{company_id}/contacts/{contact_id}",),
    ),
    ActionSpec(
        name="set_company_note",
        description="Replace the person's note on a company with the text they gave.",
        args=NoteArgs,
        kind="small",
        private=True,
        handler=set_note_action,
        undo=put_note_back,
        current=_note_now,
        invalidate=INVALIDATE,
        mirrors=("PUT /companies/{company_id}/note",),
    ),
)
