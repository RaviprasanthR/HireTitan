"""Preferences endpoints (contracts/rest-api.md, "Preferences").

Type problems are reported by FastAPI as per-field 422s; rule problems (FR-025) by the
domain as the same shape, so the form can mark each field.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.web.problems import ProblemError
from hiretitan.preferences.application.service import (
    PreferencesInvalid,
    get_preferences,
    get_suggestions,
    save_preferences,
)
from hiretitan.preferences.domain.model import Pay, Place, Preferences
from hiretitan.preferences.infra.repo import PreferencesRepo
from hiretitan.profile.application.versions import CurrentProfileReader


@dataclass(frozen=True)
class PreferencesApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    clock: ClockPort
    profile_reader: Callable[[AsyncSession], CurrentProfileReader]


class PlaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str | None = None
    country: str

    @classmethod
    def from_domain(cls, place: Place) -> PlaceModel:
        return cls(city=place.city, country=place.country)

    def to_domain(self) -> Place:
        return Place(self.city, self.country)


class PayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: str
    min_annual: Decimal | None = None
    target_annual: Decimal | None = None
    basis: str


class PreferencesModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_roles: list[str]
    seniority_levels: list[str]
    years_experience: Decimal | None = None
    key_skills: list[str]
    preferred_locations: list[PlaceModel]
    default_country: str
    work_modes: list[str]
    willing_to_relocate: bool
    blocked_locations: list[PlaceModel]
    job_types: list[str]
    pay: PayModel
    notice_period_days: int | None = None
    earliest_start_date: date | None = None
    preferred_companies: list[str]
    avoided_companies: list[str]

    @classmethod
    def from_domain(cls, p: Preferences) -> PreferencesModel:
        return cls(
            target_roles=list(p.target_roles),
            seniority_levels=list(p.seniority_levels),
            years_experience=p.years_experience,
            key_skills=list(p.key_skills),
            preferred_locations=[PlaceModel.from_domain(x) for x in p.preferred_locations],
            default_country=p.default_country,
            work_modes=sorted(p.work_modes),
            willing_to_relocate=p.willing_to_relocate,
            blocked_locations=[PlaceModel.from_domain(x) for x in p.blocked_locations],
            job_types=sorted(p.job_types),
            pay=PayModel(
                currency=p.pay.currency,
                min_annual=p.pay.min_annual,
                target_annual=p.pay.target_annual,
                basis=p.pay.basis,
            ),
            notice_period_days=p.notice_period_days,
            earliest_start_date=p.earliest_start_date,
            preferred_companies=list(p.preferred_companies),
            avoided_companies=list(p.avoided_companies),
        )

    def to_domain(self) -> Preferences:
        return Preferences(
            target_roles=tuple(self.target_roles),
            seniority_levels=tuple(self.seniority_levels),
            years_experience=self.years_experience,
            key_skills=tuple(self.key_skills),
            preferred_locations=tuple(x.to_domain() for x in self.preferred_locations),
            default_country=self.default_country,
            work_modes=frozenset(self.work_modes),
            willing_to_relocate=self.willing_to_relocate,
            blocked_locations=tuple(x.to_domain() for x in self.blocked_locations),
            job_types=frozenset(self.job_types),
            pay=Pay(self.pay.currency, self.pay.min_annual, self.pay.target_annual, self.pay.basis),
            notice_period_days=self.notice_period_days,
            earliest_start_date=self.earliest_start_date,
            preferred_companies=tuple(self.preferred_companies),
            avoided_companies=tuple(self.avoided_companies),
        )


class SuggestionsOut(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    key_skills: list[str] = Field(default_factory=list)


class PreferencesOut(BaseModel):
    content: PreferencesModel
    saved_at: datetime | None
    suggestions: SuggestionsOut


class SavedOut(BaseModel):
    saved_at: datetime


def create_preferences_router(deps: PreferencesApiDeps) -> APIRouter:
    router = APIRouter(prefix="/preferences", tags=["preferences"])

    @router.get("")
    async def read_preferences() -> PreferencesOut:
        async with deps.sessions() as session:
            store = PreferencesRepo(session)
            stored = await get_preferences(store)
            ideas = await get_suggestions(store, deps.profile_reader(session))
        return PreferencesOut(
            content=PreferencesModel.from_domain(stored.content),
            saved_at=stored.saved_at,
            suggestions=SuggestionsOut(
                target_roles=list(ideas.target_roles), key_skills=list(ideas.key_skills)
            ),
        )

    @router.put("")
    async def write_preferences(body: PreferencesModel) -> SavedOut:
        async with deps.sessions() as session:
            try:
                saved_at = await save_preferences(
                    PreferencesRepo(session), deps.clock, body.to_domain()
                )
            except PreferencesInvalid as invalid:
                raise ProblemError(
                    422,
                    "Some fields are not valid.",
                    errors=[{"field": e.path, "message": e.message} for e in invalid.errors],
                ) from invalid
            await session.commit()
        return SavedOut(saved_at=saved_at)

    return router
