"""Search rules endpoints (contracts/rest-api.md, "Search rules")."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.web.problems import ProblemError
from hiretitan.search.application.ports import ProposalSource
from hiretitan.search.application.rules import (
    NoProposalError,
    RuleSetView,
    RulesService,
    RulesUnavailableError,
)
from hiretitan.search.domain.rules import (
    EFFECTS,
    LocationRule,
    RuleItem,
    RulesInvalidError,
    SearchRules,
)
from hiretitan.search.infra.repos import RuleSetsRepo


@dataclass(frozen=True)
class SearchRulesApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    source: Callable[[AsyncSession], ProposalSource]
    synonyms: Mapping[str, tuple[str, ...]]


class RuleItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    origin: str = "user"
    effect: str | None = None  # output only; ignored on input


class PlaceRuleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str | None = None
    country: str | None = None
    origin: str = "user"
    effect: str | None = None


class SearchRulesModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title_words: list[RuleItemModel]
    title_avoid: list[RuleItemModel]
    blocked_locations: list[PlaceRuleModel]
    max_age_days: int
    stack_keywords: list[RuleItemModel]
    preferred_locations: list[PlaceRuleModel]
    work_modes: list[str]
    seniority: list[str]
    years_experience: Decimal | None

    @classmethod
    def from_domain(cls, rules: SearchRules) -> SearchRulesModel:
        def items(kind: str, values: tuple[RuleItem, ...]) -> list[RuleItemModel]:
            return [
                RuleItemModel(text=i.text, origin=i.origin, effect=EFFECTS[kind]) for i in values
            ]

        def places(kind: str, values: tuple[LocationRule, ...]) -> list[PlaceRuleModel]:
            return [
                PlaceRuleModel(
                    city=p.city, country=p.country, origin=p.origin, effect=EFFECTS[kind]
                )
                for p in values
            ]

        return cls(
            title_words=items("title_words", rules.title_words),
            title_avoid=items("title_avoid", rules.title_avoid),
            blocked_locations=places("blocked_locations", rules.blocked_locations),
            max_age_days=rules.max_age_days,
            stack_keywords=items("stack_keywords", rules.stack_keywords),
            preferred_locations=places("preferred_locations", rules.preferred_locations),
            work_modes=sorted(rules.work_modes),
            seniority=list(rules.seniority),
            years_experience=rules.years_experience,
        )

    def to_domain(self) -> SearchRules:
        return SearchRules(
            title_words=tuple(RuleItem(i.text, i.origin) for i in self.title_words),
            title_avoid=tuple(RuleItem(i.text, i.origin) for i in self.title_avoid),
            blocked_locations=tuple(
                LocationRule(p.city, p.country, p.origin) for p in self.blocked_locations
            ),
            max_age_days=self.max_age_days,
            stack_keywords=tuple(RuleItem(i.text, i.origin) for i in self.stack_keywords),
            preferred_locations=tuple(
                LocationRule(p.city, p.country, p.origin) for p in self.preferred_locations
            ),
            work_modes=frozenset(self.work_modes),
            seniority=tuple(self.seniority),
            years_experience=self.years_experience,
        )


class RuleSetOut(BaseModel):
    id: UUID
    version: int
    status: str
    rules: SearchRulesModel
    based_on: dict[str, Any]
    approved_at: datetime | None


class RulesStateOut(BaseModel):
    approved: RuleSetOut | None
    proposal: RuleSetOut | None
    stale: bool


def _invalid(invalid: RulesInvalidError) -> ProblemError:
    return ProblemError(
        422,
        "Some fields are not valid.",
        errors=[{"field": e.field, "message": e.message} for e in invalid.errors],
    )


def _no_proposal(action: str) -> ProblemError:
    return ProblemError(409, f"There is no proposal to {action}.", reason="no_proposal")


def _unavailable(error: RulesUnavailableError) -> ProblemError:
    text = {
        "no_confirmed_profile": "Confirm your profile first.",
        "no_preferences": "Save your preferences first.",
    }[error.reason]
    return ProblemError(409, text, reason=error.reason)


def create_search_rules_router(deps: SearchRulesApiDeps) -> APIRouter:
    router = APIRouter(prefix="/search/rules", tags=["search"])

    def service(session: AsyncSession) -> RulesService:
        return RulesService(RuleSetsRepo(session), deps.source(session), deps.synonyms)

    async def render(session: AsyncSession, view: RuleSetView) -> RuleSetOut:
        row = await RuleSetsRepo(session).get(view.id)
        assert row is not None
        return RuleSetOut(
            id=view.id,
            version=view.version,
            status=view.status,
            rules=SearchRulesModel.from_domain(view.rules),
            based_on=row.based_on,
            approved_at=view.approved_at,
        )

    @router.get("")
    async def read_rules() -> RulesStateOut:
        async with deps.sessions() as session:
            svc = service(session)
            approved, proposal = await svc.current()
            return RulesStateOut(
                approved=await render(session, approved) if approved else None,
                proposal=await render(session, proposal) if proposal else None,
                stale=await svc.is_stale(),
            )

    @router.post("/proposal", status_code=201)
    async def make_proposal() -> RuleSetOut:
        async with deps.sessions() as session:
            try:
                view = await service(session).propose()
            except RulesUnavailableError as error:
                raise _unavailable(error) from error
            await session.commit()
            return await render(session, view)

    @router.put("/proposal")
    async def edit_proposal(body: SearchRulesModel) -> RuleSetOut:
        async with deps.sessions() as session:
            try:
                view = await service(session).edit_proposal(body.to_domain())
            except RulesInvalidError as invalid:
                raise _invalid(invalid) from invalid
            except NoProposalError as error:
                raise _no_proposal("edit") from error
            await session.commit()
            return await render(session, view)

    @router.post("/proposal/approve")
    async def approve() -> RuleSetOut:
        async with deps.sessions() as session:
            try:
                view = await service(session).approve()
            except RulesInvalidError as invalid:
                raise _invalid(invalid) from invalid
            except NoProposalError as error:
                raise _no_proposal("approve") from error
            await session.commit()
            return await render(session, view)

    @router.delete("/proposal", status_code=204)
    async def discard() -> Response:
        async with deps.sessions() as session:
            await service(session).discard_proposal()
            await session.commit()
        return Response(status_code=204)

    return router
