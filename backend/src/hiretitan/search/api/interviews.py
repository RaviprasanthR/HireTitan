"""Interview tracking endpoints (feature 002e, contracts/rest-api.md).

The person's own notes about a job in their pipeline. Nothing here sends anything to a contact
or hands data to an AI step (FR-010).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.web.problems import ProblemError
from hiretitan.search.application.interviews import (
    InterviewView,
    JobNotFoundError,
    read_interview,
)
from hiretitan.search.infra.repos import InterviewsRepo, JobsRepo


@dataclass(frozen=True)
class SearchInterviewsApiDeps:
    sessions: async_sessionmaker[AsyncSession]


class ContactOut(BaseModel):
    name: str
    role: str | None
    email: str | None
    phone: str | None
    linkedin_url: str | None


class SourceOut(BaseModel):
    kind: Literal["direct", "hiring_firm"]
    firm_name: str | None


class QuestionOut(BaseModel):
    id: UUID
    position: int
    question: str
    answer: str | None


class RoundOut(BaseModel):
    id: UUID
    number: int
    kind: Literal["screening", "technical", "hr", "managerial", "other"]
    state: Literal["scheduled", "cleared", "failed"]
    scheduled_at: datetime | None
    interviewers: str | None
    feedback: str | None
    questions: list[QuestionOut]


class InterviewStatusOut(BaseModel):
    # a job outside the pipeline (read-only on its page) has no round, so its own state shows
    state: Literal["explore", "skipped", "applied", "inquired", "scheduled", "cleared", "failed"]
    round: int | None


class InterviewOut(BaseModel):
    job_id: UUID
    can_edit: bool
    can_add_round: bool
    contact: ContactOut | None
    source: SourceOut | None
    rounds: list[RoundOut]
    status: InterviewStatusOut


def _out(view: InterviewView) -> InterviewOut:
    return InterviewOut.model_validate(asdict(view))


def _no_job() -> ProblemError:
    return ProblemError(404, "That job does not exist.")


def create_interviews_router(deps: SearchInterviewsApiDeps) -> APIRouter:
    router = APIRouter(tags=["interviews"])

    @router.get("/jobs/{job_id}/interview", response_model=InterviewOut)
    async def read(job_id: UUID) -> InterviewOut:
        async with deps.sessions() as session:
            try:
                view = await read_interview(JobsRepo(session), InterviewsRepo(session), job_id)
            except JobNotFoundError as error:
                raise _no_job() from error
        return _out(view)

    return router
