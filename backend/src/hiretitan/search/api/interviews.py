"""Interview tracking endpoints (feature 002e, contracts/rest-api.md).

The person's own notes about a job in their pipeline. Nothing here sends anything to a contact
or hands data to an AI step (FR-010).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.web.problems import ProblemError, problem
from hiretitan.search.api.models import ResumeChoiceOut
from hiretitan.search.application.interviews import (
    InterviewInputError,
    InterviewView,
    JobNotFoundError,
    NotInPipelineError,
    ProcessFailedError,
    QuestionNotFoundError,
    RoundNotFoundError,
    add_question,
    add_round,
    read_interview,
    remove_contact,
    remove_question,
    remove_round,
    save_contact,
    save_source,
    update_question,
    update_round,
)
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.repos import JobsRepo


@dataclass(frozen=True)
class SearchInterviewsApiDeps:
    sessions: async_sessionmaker[AsyncSession]


class PipelineContactOut(BaseModel):
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
    contact: PipelineContactOut | None
    source: SourceOut | None
    rounds: list[RoundOut]
    status: InterviewStatusOut
    resume: ResumeChoiceOut


class ContactIn(BaseModel):
    # a default, so a missing name is reported field by field like any other bad value
    name: str = Field(default="", max_length=2_000)
    role: str | None = Field(default=None, max_length=2_000)
    email: str | None = Field(default=None, max_length=2_000)
    phone: str | None = Field(default=None, max_length=2_000)
    linkedin_url: str | None = Field(default=None, max_length=2_000)


class SourceIn(BaseModel):
    kind: str | None = Field(default=None, max_length=100)
    firm_name: str | None = Field(default=None, max_length=2_000)


class RoundIn(BaseModel):
    # the kind is checked against the list by the domain so the field error reads the same as the
    # others; the length caps here only stop an absurd body before it is read
    kind: str = ""
    scheduled_at: AwareDatetime | None = None
    interviewers: str | None = Field(default=None, max_length=20_000)


class RoundPatch(BaseModel):
    kind: str | None = None
    scheduled_at: AwareDatetime | None = None
    interviewers: str | None = Field(default=None, max_length=20_000)
    state: str | None = None
    feedback: str | None = Field(default=None, max_length=100_000)


# The caps below only stop an absurd body; the real limits (question 2,000, answer 10,000) are the
# domain's, so the person gets a field error that names them.
class QuestionIn(BaseModel):
    question: str = Field(default="", max_length=20_000)
    answer: str | None = Field(default=None, max_length=100_000)


class QuestionPatch(BaseModel):
    question: str | None = Field(default=None, max_length=20_000)
    answer: str | None = Field(default=None, max_length=100_000)


def _out(view: InterviewView) -> InterviewOut:
    return InterviewOut.model_validate(asdict(view))


def _no_job() -> ProblemError:
    return ProblemError(404, "That job does not exist.")


def _not_in_pipeline(error: NotInPipelineError) -> ProblemError:
    return ProblemError(409, str(error), reason="not_in_pipeline")


def _no_round() -> ProblemError:
    return ProblemError(404, "That round does not exist.")


def _no_question() -> ProblemError:
    return ProblemError(404, "That question does not exist.")


def _process_failed(error: ProcessFailedError) -> ProblemError:
    return ProblemError(409, str(error), reason="process_failed")


def _invalid(error: InterviewInputError) -> Any:
    return problem(
        422,
        str(error),
        errors=[{"field": e.field, "message": e.message} for e in error.errors],
    )


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

    @router.put("/jobs/{job_id}/interview/contact", response_model=InterviewOut)
    async def put_contact(job_id: UUID, body: ContactIn) -> Any:
        async with deps.sessions() as session:
            jobs, store = JobsRepo(session), InterviewsRepo(session)
            try:
                await save_contact(jobs, store, job_id, **body.model_dump())
                view = await read_interview(jobs, store, job_id)
            except JobNotFoundError as error:
                raise _no_job() from error
            except NotInPipelineError as error:
                raise _not_in_pipeline(error) from error
            except InterviewInputError as error:
                return _invalid(error)
            await session.commit()
        return _out(view)

    @router.delete("/jobs/{job_id}/interview/contact", response_model=InterviewOut)
    async def delete_contact(job_id: UUID) -> InterviewOut:
        async with deps.sessions() as session:
            jobs, store = JobsRepo(session), InterviewsRepo(session)
            try:
                await remove_contact(jobs, store, job_id)
                view = await read_interview(jobs, store, job_id)
            except JobNotFoundError as error:
                raise _no_job() from error
            except NotInPipelineError as error:
                raise _not_in_pipeline(error) from error
            await session.commit()
        return _out(view)

    @router.put("/jobs/{job_id}/interview/source", response_model=InterviewOut)
    async def put_source(job_id: UUID, body: SourceIn) -> Any:
        async with deps.sessions() as session:
            jobs, store = JobsRepo(session), InterviewsRepo(session)
            try:
                await save_source(jobs, store, job_id, kind=body.kind, firm_name=body.firm_name)
                view = await read_interview(jobs, store, job_id)
            except JobNotFoundError as error:
                raise _no_job() from error
            except NotInPipelineError as error:
                raise _not_in_pipeline(error) from error
            except InterviewInputError as error:
                return _invalid(error)
            await session.commit()
        return _out(view)

    @router.post("/jobs/{job_id}/interview/rounds", response_model=InterviewOut, status_code=201)
    async def post_round(job_id: UUID, body: RoundIn) -> Any:
        async with deps.sessions() as session:
            jobs, store = JobsRepo(session), InterviewsRepo(session)
            try:
                await add_round(jobs, store, job_id, **body.model_dump())
                view = await read_interview(jobs, store, job_id)
            except JobNotFoundError as error:
                raise _no_job() from error
            except NotInPipelineError as error:
                raise _not_in_pipeline(error) from error
            except ProcessFailedError as error:
                raise _process_failed(error) from error
            except InterviewInputError as error:
                return _invalid(error)
            await session.commit()
        return _out(view)

    @router.patch("/interview/rounds/{round_id}", response_model=InterviewOut)
    async def patch_round(round_id: UUID, body: RoundPatch) -> Any:
        async with deps.sessions() as session:
            jobs, store = JobsRepo(session), InterviewsRepo(session)
            try:
                job_id = await update_round(
                    jobs, store, round_id, body.model_dump(exclude_unset=True)
                )
                view = await read_interview(jobs, store, job_id)
            except (JobNotFoundError, RoundNotFoundError) as error:
                raise _no_round() from error
            except NotInPipelineError as error:
                raise _not_in_pipeline(error) from error
            except InterviewInputError as error:
                return _invalid(error)
            await session.commit()
        return _out(view)

    @router.delete("/interview/rounds/{round_id}", response_model=InterviewOut)
    async def delete_round(round_id: UUID) -> InterviewOut:
        async with deps.sessions() as session:
            jobs, store = JobsRepo(session), InterviewsRepo(session)
            try:
                job_id = await remove_round(jobs, store, round_id)
                view = await read_interview(jobs, store, job_id)
            except (JobNotFoundError, RoundNotFoundError) as error:
                raise _no_round() from error
            except NotInPipelineError as error:
                raise _not_in_pipeline(error) from error
            await session.commit()
        return _out(view)

    @router.post(
        "/interview/rounds/{round_id}/questions", response_model=InterviewOut, status_code=201
    )
    async def post_question(round_id: UUID, body: QuestionIn) -> Any:
        async with deps.sessions() as session:
            jobs, store = JobsRepo(session), InterviewsRepo(session)
            try:
                job_id = await add_question(jobs, store, round_id, **body.model_dump())
                view = await read_interview(jobs, store, job_id)
            except (JobNotFoundError, RoundNotFoundError) as error:
                raise _no_round() from error
            except NotInPipelineError as error:
                raise _not_in_pipeline(error) from error
            except InterviewInputError as error:
                return _invalid(error)
            await session.commit()
        return _out(view)

    @router.patch("/interview/questions/{question_id}", response_model=InterviewOut)
    async def patch_question(question_id: UUID, body: QuestionPatch) -> Any:
        async with deps.sessions() as session:
            jobs, store = JobsRepo(session), InterviewsRepo(session)
            try:
                job_id = await update_question(
                    jobs, store, question_id, body.model_dump(exclude_unset=True)
                )
                view = await read_interview(jobs, store, job_id)
            except (JobNotFoundError, QuestionNotFoundError) as error:
                raise _no_question() from error
            except NotInPipelineError as error:
                raise _not_in_pipeline(error) from error
            except InterviewInputError as error:
                return _invalid(error)
            await session.commit()
        return _out(view)

    @router.delete("/interview/questions/{question_id}", response_model=InterviewOut)
    async def delete_question(question_id: UUID) -> InterviewOut:
        async with deps.sessions() as session:
            jobs, store = JobsRepo(session), InterviewsRepo(session)
            try:
                job_id = await remove_question(jobs, store, question_id)
                view = await read_interview(jobs, store, job_id)
            except (JobNotFoundError, QuestionNotFoundError) as error:
                raise _no_question() from error
            except NotInPipelineError as error:
                raise _not_in_pipeline(error) from error
            await session.commit()
        return _out(view)

    return router
