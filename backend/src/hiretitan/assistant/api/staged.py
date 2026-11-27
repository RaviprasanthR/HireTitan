"""The chat's post-to-draft flow (002m quick flow): choose a draft, paste a post, say yes or no."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.application.ports import (
    DraftRefusedError,
    StagedFlow,
    StagedRefusedError,
    StagedStep,
    StagedView,
)
from hiretitan.assistant.domain.quick import DraftKind
from hiretitan.platform.web.problems import ProblemError


class StagedOut(BaseModel):
    step: StagedStep
    kind: DraftKind | None
    label: str | None
    job_ref: str | None
    draft_ref: str | None
    already_saved: bool


class BeginIn(BaseModel):
    kind: DraftKind


class PostIn(BaseModel):
    text: str = Field(min_length=1, max_length=40_000)


class DetailsIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=120)


class SavedOut(BaseModel):
    summary: str


def _out(view: StagedView) -> StagedOut:
    kind: DraftKind | None = view.kind  # type: ignore[assignment]
    return StagedOut(
        step=view.step,
        kind=kind,
        label=view.label,
        job_ref=view.job_ref,
        draft_ref=view.draft_ref,
        already_saved=view.already_saved,
    )


def create_staged_router(deps: AssistantApiDeps) -> APIRouter:
    router = APIRouter(
        prefix="/assistant/conversations/{conversation_id}/staged", tags=["assistant"]
    )

    def flow() -> StagedFlow:
        if deps.staged is None:
            raise ProblemError(503, "Drafts are not available here.", reason="unavailable")
        return deps.staged

    async def known(conversation_id: UUID) -> None:
        if not await deps.turn.store.conversation_exists(conversation_id):
            raise ProblemError(404, "That conversation does not exist.", reason="not_found")

    async def run(step: object) -> StagedOut:
        try:
            view = await step  # type: ignore[misc]
        except StagedRefusedError as error:
            raise ProblemError(422, error.message, reason="staged_refused") from error
        except DraftRefusedError as error:
            raise ProblemError(409, error.message, reason="draft_refused") from error
        return _out(view)

    @router.get("", response_model=StagedOut | None)
    async def view(conversation_id: UUID) -> StagedOut | None:
        await known(conversation_id)
        current = await flow().view(conversation_id)
        return _out(current) if current is not None else None

    @router.post("/begin", response_model=StagedOut)
    async def begin(conversation_id: UUID, body: BeginIn) -> StagedOut:
        await known(conversation_id)
        return await run(flow().begin(conversation_id, body.kind))

    @router.post("/post", response_model=StagedOut)
    async def post(conversation_id: UUID, body: PostIn) -> StagedOut:
        await known(conversation_id)
        return await run(flow().hold_post(conversation_id, body.text))

    @router.post("/details", response_model=StagedOut)
    async def details(conversation_id: UUID, body: DetailsIn) -> StagedOut:
        await known(conversation_id)
        return await run(flow().details(conversation_id, body.title, body.company))

    @router.post("/choose", response_model=StagedOut)
    async def choose(conversation_id: UUID, body: BeginIn) -> StagedOut:
        await known(conversation_id)
        return await run(flow().choose(conversation_id, body.kind))

    @router.post("/save", response_model=SavedOut)
    async def save(conversation_id: UUID) -> SavedOut:
        await known(conversation_id)
        try:
            return SavedOut(summary=await flow().save(conversation_id))
        except StagedRefusedError as error:
            raise ProblemError(422, error.message, reason="staged_refused") from error

    @router.post("/discard", status_code=204)
    async def discard(conversation_id: UUID) -> None:
        await known(conversation_id)
        await flow().discard(conversation_id)

    _ = Literal  # the step names are typed in the ports
    return router
