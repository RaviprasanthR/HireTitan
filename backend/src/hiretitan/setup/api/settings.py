"""Settings endpoints (contracts/rest-api.md, "Setup: status, settings, data").

The key never appears here: only its status. The tier models are fixed defaults and
read-only in this slice (clarification Q2), so a request that mentions them is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.llm.infra.calls_repo import CallsRepo
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.runtime.domain.run_state import PauseReason
from hiretitan.platform.runtime.resume_paused import resume_paused_runs
from hiretitan.platform.runtime.runner import RunQueue
from hiretitan.platform.web.problems import ProblemError
from hiretitan.setup.application.settings import (
    BudgetCapInvalid,
    SettingsView,
    TierModel,
    update_budget_cap,
)
from hiretitan.setup.application.status import get_ai_status
from hiretitan.setup.infra.settings_repo import SettingsRepo

TIER_ORDER = ("fast", "strong")


@dataclass(frozen=True)
class SettingsApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    queue: RunQueue
    clock: ClockPort
    provider: str


class TierOut(BaseModel):
    tier: str
    provider: str
    model: str


class SettingsOut(BaseModel):
    budget_cap_usd: Decimal
    spent_this_month_usd: Decimal
    tiers: list[TierOut]
    key_status: str


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    budget_cap_usd: Decimal = Field(ge=0, le=10_000, allow_inf_nan=False)


async def load_settings(deps: SettingsApiDeps, session: AsyncSession) -> SettingsView:
    now = deps.clock.now()
    tiers = ModelCatalog.load().tiers.get(deps.provider, {})
    ai = await get_ai_status(ProviderStatusRepo(session), deps.provider)
    return SettingsView(
        budget_cap_usd=await SettingsRepo(session).read_budget_cap(),
        spent_this_month_usd=await CallsRepo(session).spent_in_month(now.year, now.month),
        tiers=tuple(
            TierModel(tier, deps.provider, tiers[tier]) for tier in TIER_ORDER if tier in tiers
        ),
        key_status=ai.status,
        key_message=ai.message,
    )


def create_settings_router(deps: SettingsApiDeps) -> APIRouter:
    router = APIRouter(prefix="/settings", tags=["settings"])

    @router.get("")
    async def read_settings() -> SettingsOut:
        async with deps.sessions() as session:
            view = await load_settings(deps, session)
        return SettingsOut(
            budget_cap_usd=view.budget_cap_usd,
            spent_this_month_usd=view.spent_this_month_usd,
            tiers=[TierOut(tier=t.tier, provider=t.provider, model=t.model) for t in view.tiers],
            key_status=view.key_status,
        )

    @router.put("")
    async def write_settings(body: SettingsIn) -> dict[str, str]:
        woken = False

        async def on_raised() -> None:
            nonlocal woken
            woken = True

        async with deps.sessions() as session:
            try:
                await update_budget_cap(SettingsRepo(session), body.budget_cap_usd, on_raised)
            except BudgetCapInvalid as invalid:
                raise ProblemError(
                    422,
                    "Some fields are not valid.",
                    errors=[{"field": "budget_cap_usd", "message": str(invalid)}],
                ) from invalid
            await session.commit()
        if woken:  # after the commit, so the woken runs see the new cap
            await resume_paused_runs(deps.sessions, deps.queue, PauseReason.budget_reached)
        return {"status": "saved"}

    return router
