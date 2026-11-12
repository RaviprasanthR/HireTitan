"""Status endpoints (contracts/rest-api.md, "Setup: status, data").

One call powers the banner and Home. The key never appears: only its status.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.setup.application.status import SetupFacts, get_status


@dataclass(frozen=True)
class StatusApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    clock: ClockPort
    provider: str
    facts: Callable[[AsyncSession], SetupFacts]
    enqueue_key_check: Callable[[], Awaitable[None]]


class AiOut(BaseModel):
    provider: str
    status: str
    message: str | None
    checked_at: datetime | None


class ChecklistOut(BaseModel):
    key_ok: bool
    resume_uploaded: bool
    profile_confirmed: bool
    preferences_saved: bool
    rules_approved: bool
    searched_once: bool


class StatusOut(BaseModel):
    ai: AiOut
    checklist: ChecklistOut


def create_status_router(deps: StatusApiDeps) -> APIRouter:
    router = APIRouter(prefix="/status", tags=["status"])

    @router.get("")
    async def read_status() -> StatusOut:
        async with deps.sessions() as session:
            status = await get_status(
                provider=deps.provider,
                providers=ProviderStatusRepo(session),
                facts=deps.facts(session),
                now=deps.clock.now(),
            )
        ai, checklist = status.ai, status.checklist
        return StatusOut(
            ai=AiOut(
                provider=ai.provider,
                status=ai.status,
                message=ai.message,
                checked_at=ai.checked_at,
            ),
            checklist=ChecklistOut(
                key_ok=checklist.key_ok,
                resume_uploaded=checklist.resume_uploaded,
                profile_confirmed=checklist.profile_confirmed,
                preferences_saved=checklist.preferences_saved,
                rules_approved=checklist.rules_approved,
                searched_once=checklist.searched_once,
            ),
        )

    @router.post("/ai/check", status_code=202)
    async def check_again() -> dict[str, str]:
        await deps.enqueue_key_check()
        return {"status": "queued"}

    return router
