"""Mikasa's actions on the person's contacts and company notes (002m contracts/actions.md).

Private (002b FR-022, research R5): the model sees only refs and labels built from the company's
name. The panel fills in names, roles and the note from the existing endpoints.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from hiretitan.actions.refs import Ref, label_contact, label_note
from hiretitan.actions.spec import (
    ActionContext,
    ActionError,
    ActionSpec,
    PrivateItem,
    PrivateResult,
)
from hiretitan.actions.text import bounded
from hiretitan.search.infra.models import CompanyRow, ContactRow
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, NotesRepo

COMPANY_NOT_FOUND = ActionError("not_found", "That company is not in HireTitan.")


async def company_name(ctx: ActionContext, company_id: UUID) -> str | None:
    row = await CompaniesRepo(ctx.session).get(company_id)
    if row is None or row.deleted_at is not None:
        return None
    return bounded(row.name).text


def _contact_items(rows: list[ContactRow], names: dict[UUID, str]) -> list[PrivateItem]:
    per_company: dict[UUID, int] = {}
    totals: dict[UUID, int] = {}
    for row in rows:
        totals[row.company_id] = totals.get(row.company_id, 0) + 1
    items = []
    for row in rows:
        per_company[row.company_id] = per_company.get(row.company_id, 0) + 1
        label = label_contact(names.get(row.company_id, "a company"))
        if totals[row.company_id] > 1:
            label += f" ({per_company[row.company_id]} of {totals[row.company_id]})"
        items.append(PrivateItem(ref=str(Ref("contact", row.id)), label=label))
    return items


class CompanyArgs(BaseModel):
    company: str = Field(description="The company's ref, like company:<id>")


async def list_contacts(ctx: ActionContext, args: CompanyArgs) -> PrivateResult | ActionError:
    company_id = Ref.parse(args.company, expect="company").id
    name = await company_name(ctx, company_id)
    if name is None:
        return COMPANY_NOT_FOUND
    rows = await ContactsRepo(ctx.session).list_for_company(company_id)
    return PrivateResult(items=_contact_items(rows, {company_id: name}), total=len(rows))


class FindContactArgs(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="All or part of the name")
    company: str | None = Field(None, description="Only at this company (a company ref)")


async def find_contact(ctx: ActionContext, args: FindContactArgs) -> PrivateResult:
    """Matches on the server; only the matches' refs go back (research R5)."""
    query = select(ContactRow, CompanyRow.name).join(
        CompanyRow, CompanyRow.id == ContactRow.company_id
    )
    if args.company:
        query = query.where(ContactRow.company_id == Ref.parse(args.company, expect="company").id)
    query = query.where(CompanyRow.deleted_at.is_(None)).order_by(CompanyRow.name, ContactRow.id)
    wanted = args.name.casefold().strip()
    found = [
        (row, name)
        for row, name in (await ctx.session.execute(query)).all()
        if wanted in row.name.casefold()
    ]
    names = {row.company_id: bounded(name).text for row, name in found}
    rows = [row for row, _ in found]
    return PrivateResult(items=_contact_items(rows, names), total=len(rows))


async def get_company_note(ctx: ActionContext, args: CompanyArgs) -> PrivateResult | ActionError:
    company_id = Ref.parse(args.company, expect="company").id
    name = await company_name(ctx, company_id)
    if name is None:
        return COMPANY_NOT_FOUND
    if await NotesRepo(ctx.session).get(company_id) is None:
        return PrivateResult(items=[], total=0)
    return PrivateResult(
        items=[PrivateItem(ref=str(Ref("note", company_id)), label=label_note(name))], total=1
    )


READS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="list_contacts",
        description="The person's contacts at a company, as refs. The app shows who they are; "
        "you never see their details.",
        args=CompanyArgs,
        kind="read",
        private=True,
        handler=list_contacts,
        mirrors=("GET /companies/{company_id}/contacts",),
    ),
    ActionSpec(
        name="find_contact",
        description="Find a contact by name (optionally at one company). Returns refs only.",
        args=FindContactArgs,
        kind="read",
        private=True,
        handler=find_contact,
    ),
    ActionSpec(
        name="get_company_note",
        description="The person's note on a company, as a ref the app shows. You never see it.",
        args=CompanyArgs,
        kind="read",
        private=True,
        handler=get_company_note,
    ),
)
