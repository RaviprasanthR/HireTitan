"""``GET /assistant/status``: can Mikasa be used now (FR-024)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from hiretitan.assistant.api.deps import AssistantApiDeps


class AssistantStatusOut(BaseModel):
    available: bool
    reason: str | None = None
    provider_message: str | None = None


def create_status_router(deps: AssistantApiDeps) -> APIRouter:
    router = APIRouter(prefix="/assistant", tags=["assistant"])

    @router.get("/status", response_model=AssistantStatusOut)
    async def status() -> AssistantStatusOut:
        found = await deps.status()
        return AssistantStatusOut(
            available=found.available,
            reason=found.reason,
            provider_message=found.provider_message,
        )

    return router
