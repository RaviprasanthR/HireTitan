"""The review list: everything waiting for the user (FR-033)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.setup.application.review_items import build_review_items
from hiretitan.setup.application.status import SetupFacts


@dataclass(frozen=True)
class ReviewItemsApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    facts: Callable[[AsyncSession], SetupFacts]


class ReviewItemOut(BaseModel):
    id: UUID
    kind: str
    title: str
    target: str
    updated_at: datetime


def create_review_items_router(deps: ReviewItemsApiDeps) -> APIRouter:
    router = APIRouter(tags=["review"])

    @router.get("/review-items")
    async def list_review_items() -> list[ReviewItemOut]:
        async with deps.sessions() as session:
            runs = await RunsRepo(session).list_by_status(
                RunStatus.awaiting_review, RunStatus.paused
            )
            items = await build_review_items(runs, deps.facts(session))
        return [
            ReviewItemOut(
                id=i.id, kind=i.kind, title=i.title, target=i.target, updated_at=i.updated_at
            )
            for i in items
        ]

    return router
