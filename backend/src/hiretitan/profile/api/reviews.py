"""Profile review endpoints (contracts/rest-api.md, "Profile reviews")."""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel

from hiretitan.platform.runtime.domain.run_state import IllegalTransitionError, RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.runtime.runner import resume_run
from hiretitan.platform.web.problems import ProblemError
from hiretitan.profile.api.resumes import ProfileApiDeps
from hiretitan.profile.api.schemas import ProfileContentModel
from hiretitan.profile.application.reviews import (
    CLOSED,
    ReviewConflictError,
    check_confirm,
    require_open,
)
from hiretitan.profile.domain.serialization import content_to_json
from hiretitan.profile.infra.repos import Review, ReviewsRepo, VersionsRepo


class ProvenanceOut(BaseModel):
    prompt_name: str
    prompt_version: str
    provider: str
    model: str


class ReviewOut(BaseModel):
    id: UUID
    run_id: UUID
    resume_file_id: UUID | None
    status: str
    extraction: ProfileContentModel
    draft: ProfileContentModel | None
    draft_saved_at: datetime | None
    dropped_items: list[dict[str, Any]]
    flags: dict[str, Any]
    compare_to: ProfileContentModel | None
    changed_paths: list[str]
    provenance: ProvenanceOut


class DraftSavedOut(BaseModel):
    draft_saved_at: datetime


class RunRef(BaseModel):
    run_id: UUID


def _not_found(review_id: UUID) -> ProblemError:
    return ProblemError(404, f"Review {review_id} was not found.")


def _conflict(error: ReviewConflictError | IllegalTransitionError) -> ProblemError:
    message = (
        str(error) if isinstance(error, ReviewConflictError) else "This is no longer possible."
    )
    return ProblemError(409, message)


def create_reviews_router(deps: ProfileApiDeps) -> APIRouter:
    router = APIRouter(prefix="/profile/reviews", tags=["profile reviews"])

    async def load(review_id: UUID) -> Review:
        async with deps.sessions() as session:
            review = await ReviewsRepo(session).get(review_id)
        if review is None:
            raise _not_found(review_id)
        return review

    @router.get("/{review_id}")
    async def get_review(review_id: UUID) -> ReviewOut:
        review = await load(review_id)
        async with deps.sessions() as session:
            compare = (
                await VersionsRepo(session).get(review.compare_to_version_id)
                if review.compare_to_version_id
                else None
            )
        return ReviewOut(
            id=review.id,
            run_id=review.run_id,
            resume_file_id=review.resume_file_id,
            status=review.status,
            extraction=ProfileContentModel.from_json(review.extraction),
            draft=ProfileContentModel.from_domain(review.draft) if review.draft else None,
            draft_saved_at=review.draft_saved_at,
            dropped_items=review.dropped_items,
            flags=review.flags,
            compare_to=ProfileContentModel.from_domain(compare.content) if compare else None,
            changed_paths=review.changed_paths,
            provenance=ProvenanceOut(
                prompt_name=review.provenance.prompt_name,
                prompt_version=review.provenance.prompt_version,
                provider=review.provenance.provider,
                model=review.provenance.model,
            ),
        )

    @router.put("/{review_id}/draft")
    async def save_draft(review_id: UUID, body: ProfileContentModel) -> DraftSavedOut:
        review = await load(review_id)
        try:
            require_open(review.status)
        except ReviewConflictError as error:
            raise _conflict(error) from None
        async with deps.sessions() as session:
            saved_at = await ReviewsRepo(session).set_draft(review_id, body.to_domain())
            await session.commit()
        if saved_at is None:  # confirmed or discarded between the check and the write
            raise _conflict(ReviewConflictError(CLOSED))
        return DraftSavedOut(draft_saved_at=saved_at)

    @router.post("/{review_id}/confirm", status_code=202)
    async def confirm(review_id: UUID, body: ProfileContentModel) -> RunRef:
        review = await load(review_id)
        try:
            require_open(review.status)
        except ReviewConflictError as error:
            raise _conflict(error) from None
        content = body.to_domain()
        check = check_confirm(content)
        if not check.ok:
            raise ProblemError(
                422,
                "This profile cannot be confirmed yet.",
                errors=[{"field": e.path, "message": e.message} for e in check.errors],
            )
        try:
            await resume_run(
                deps.sessions,
                deps.queue,
                review.run_id,
                {"action": "confirm", "content": content_to_json(content)},
            )
        except IllegalTransitionError as error:
            raise _conflict(error) from None
        return RunRef(run_id=review.run_id)

    @router.post("/{review_id}/discard", status_code=204)
    async def discard(review_id: UUID) -> Response:
        review = await load(review_id)
        try:
            require_open(review.status)
        except ReviewConflictError as error:
            raise _conflict(error) from None
        async with deps.sessions() as session:
            if not await ReviewsRepo(session).set_status(review_id, "discarded"):
                raise _conflict(ReviewConflictError(CLOSED))
            # If the run is already past the point where it can be cancelled, leave it.
            with contextlib.suppress(IllegalTransitionError):
                await RunsRepo(session).transition(review.run_id, RunStatus.cancelled)
            await session.commit()
        return Response(status_code=204)

    return router
