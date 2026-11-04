"""AI status, the setup checklist and budget, for the banner and Home (FR-028 to FR-030)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatus
from hiretitan.setup.application.settings import SettingsStore, SpendReader
from hiretitan.setup.domain.checklist import Checklist, build_checklist


class ProviderStatusReader(Protocol):
    async def get(self, provider: str) -> ProviderStatus | None: ...


class SetupFacts(Protocol):
    """What other modules know, as yes/no answers (each from that module's application)."""

    async def resume_uploaded(self) -> bool: ...

    async def profile_confirmed(self) -> bool: ...

    async def preferences_saved(self) -> bool: ...

    async def open_review_id(self, run_id: UUID) -> UUID | None: ...

    async def current_open_review_id(self) -> UUID | None: ...

    async def active_run_id(self) -> UUID | None: ...


@dataclass(frozen=True, slots=True)
class AiStatus:
    provider: str
    status: str
    message: str | None
    checked_at: datetime | None


@dataclass(frozen=True, slots=True)
class Budget:
    cap_usd: Decimal
    spent_usd: Decimal
    period: str  # YYYY-MM


@dataclass(frozen=True, slots=True)
class Status:
    ai: AiStatus
    checklist: Checklist
    budget: Budget


async def get_ai_status(providers: ProviderStatusReader, provider: str) -> AiStatus:
    row = await providers.get(provider)
    if row is None:
        return AiStatus(provider, "unknown", None, None)
    return AiStatus(provider, row.status, row.message, row.checked_at)


async def get_status(
    *,
    provider: str,
    providers: ProviderStatusReader,
    settings: SettingsStore,
    spend: SpendReader,
    facts: SetupFacts,
    now: datetime,
) -> Status:
    ai = await get_ai_status(providers, provider)
    checklist = build_checklist(
        key_status=ai.status,
        resume_uploaded=await facts.resume_uploaded(),
        profile_confirmed=await facts.profile_confirmed(),
        preferences_saved=await facts.preferences_saved(),
    )
    budget = Budget(
        cap_usd=await settings.read_budget_cap(),
        spent_usd=await spend.spent_in_month(now.year, now.month),
        period=f"{now.year:04d}-{now.month:02d}",
    )
    return Status(ai, checklist, budget)
