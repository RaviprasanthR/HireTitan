"""First-run setup endpoints (contracts/rest-api.md, "First-run setup")."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.web.problems import ProblemError
from hiretitan.setup.application.onboarding import (
    OnboardingFacts,
    SetupNotReady,
    complete_setup,
    get_onboarding,
    set_display_name,
)
from hiretitan.setup.infra.settings_repo import SettingsRepo

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OnboardingApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    clock: ClockPort
    facts: Callable[[AsyncSession], OnboardingFacts]
    # runs after setup is recorded (the composition root wires "approve the first search rules");
    # a failure is logged and never fails setup (002i FR-004)
    on_completed: Callable[[], Awaitable[None]] | None = None


class OnboardingOut(BaseModel):
    step: Literal[1, 2, 3, 4, "done"]
    display_name: str | None
    open_review_id: UUID | None
    active_run_id: UUID | None


class NameIn(BaseModel):
    display_name: str


class NameOut(BaseModel):
    display_name: str


class CompletedOut(BaseModel):
    setup_completed_at: datetime


def create_onboarding_router(deps: OnboardingApiDeps) -> APIRouter:
    router = APIRouter(prefix="/onboarding", tags=["onboarding"])

    @router.get("")
    async def read_onboarding() -> OnboardingOut:
        async with deps.sessions() as session:
            view = await get_onboarding(SettingsRepo(session), deps.facts(session))
        return OnboardingOut(
            step=view.step,
            display_name=view.display_name,
            open_review_id=view.open_review_id,
            active_run_id=view.active_run_id,
        )

    @router.put("/name")
    async def write_name(body: NameIn) -> NameOut:
        async with deps.sessions() as session:
            try:
                name = await set_display_name(SettingsRepo(session), body.display_name)
            except ValueError as invalid:
                raise ProblemError(
                    422,
                    "Some fields are not valid.",
                    errors=[{"field": "display_name", "message": str(invalid)}],
                ) from invalid
            await session.commit()
        return NameOut(display_name=name)

    @router.post("/complete")
    async def complete() -> CompletedOut:
        async with deps.sessions() as session:
            facts = deps.facts(session)
            try:
                at = await complete_setup(
                    SettingsRepo(session),
                    deps.clock.now(),
                    profile_confirmed=await facts.profile_confirmed(),
                    preferences_saved=await facts.preferences_saved(),
                )
            except SetupNotReady as not_ready:
                raise ProblemError(409, str(not_ready)) from not_ready
            await session.commit()
        if deps.on_completed is not None:
            try:
                await deps.on_completed()
            except Exception:
                log.exception("Setup finished, but the follow-up step failed")
        return CompletedOut(setup_completed_at=at)

    return router
