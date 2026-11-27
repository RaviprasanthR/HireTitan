"""``GET /assistant/refs/{ref}``: what the panel shows for a ref Mikasa wrote (research R5).

The answer goes to the person's browser, never to the model, so it may hold private details.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.platform.web.problems import ProblemError


class RefCardOut(BaseModel):
    ref: str
    kind: str
    title: str
    subtitle: str | None = None
    lines: list[str] = []
    link: str | None = None


def create_refs_router(deps: AssistantApiDeps) -> APIRouter:
    router = APIRouter(prefix="/assistant/refs", tags=["assistant"])

    @router.get("/{ref}", response_model=RefCardOut)
    async def card(ref: str) -> RefCardOut:
        found = await deps.describe(ref)
        if found is None:
            raise ProblemError(404, "That item no longer exists.", reason="not_found")
        return RefCardOut(**found)

    return router
