"""Mikasa's actions on companies (002m contracts/actions.md, "Companies and contacts").

A company's own fields go to the model; its contacts and note do not. The model may learn how
many contacts there are and whether a note exists, so it can offer to show them (R5).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from hiretitan.actions.refs import Ref
from hiretitan.actions.spec import ActionContext, ActionError, ActionSpec, ReadResult
from hiretitan.actions.text import bounded
from hiretitan.search.application.companies import CompanyView, list_companies, view_of
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, PipelineCompaniesRepo

NOT_FOUND = ActionError("not_found", "That company is not in HireTitan.")


def company_ref(company_id: Any) -> str:
    return str(Ref("company", company_id))


def company_fields(view: CompanyView, contact_count: int, has_note: bool) -> dict[str, Any]:
    name = bounded(view.name)
    return {
        "ref": company_ref(view.id),
        "name": name.text,
        "city": bounded(view.city, 80).text or None,
        "website": bounded(view.website, 300).text or None,
        "careers_page": bounded(view.careers_url, 300).text or None,
        "board": view.board_status,
        "hidden": view.hidden,
        "built_in": view.origin == "built_in",
        "last_checked_at": view.last_checked_at.isoformat() if view.last_checked_at else None,
        "pipeline": view.pipeline,
        "contact_count": contact_count,
        "has_note": has_note,
        "flagged": name.flagged,
    }


class SearchCompaniesArgs(BaseModel):
    name: str | None = Field(None, max_length=120, description="Part of the company name")
    filter: Literal["all", "check_manually", "hidden"] = "all"
    limit: int = Field(20, ge=1, le=50)


async def search_companies(ctx: ActionContext, args: SearchCompaniesArgs) -> ReadResult:
    counts = await ContactsRepo(ctx.session).counts_by_company()
    pipeline = await PipelineCompaniesRepo(ctx.session).states()
    views = await list_companies(CompaniesRepo(ctx.session), args.filter, counts, pipeline)
    if args.name:
        wanted = args.name.casefold()
        views = [v for v in views if wanted in v.name.casefold()]
    shown = views[: args.limit]
    return ReadResult(
        items=[company_fields(v, *counts.get(v.id, (0, False))) for v in shown],
        total=len(views),
        truncated=len(views) > len(shown),
    )


class CompanyArgs(BaseModel):
    company: str = Field(description="The company's ref, like company:<id>")


async def get_company(ctx: ActionContext, args: CompanyArgs) -> ReadResult | ActionError:
    company_id = Ref.parse(args.company, expect="company").id
    row = await CompaniesRepo(ctx.session).get(company_id)
    if row is None or row.deleted_at is not None:
        return NOT_FOUND
    counts = await ContactsRepo(ctx.session).counts_by_company()
    pipeline = await PipelineCompaniesRepo(ctx.session).states()
    fields = company_fields(view_of(row), *counts.get(company_id, (0, False)))
    fields["pipeline"] = pipeline.get(company_id)
    return ReadResult(items=[fields], total=1)


READS: tuple[ActionSpec, ...] = (
    ActionSpec(
        name="search_companies",
        description="Find companies in the person's list by name, or list those to check by "
        "hand or hidden. Gives how many contacts each has, not who they are.",
        args=SearchCompaniesArgs,
        kind="read",
        handler=search_companies,
        mirrors=("GET /companies",),
    ),
    ActionSpec(
        name="get_company",
        description="One company's details by its ref.",
        args=CompanyArgs,
        kind="read",
        handler=get_company,
    ),
)
