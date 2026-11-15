"""Pipeline endpoints (feature 002f, contracts/rest-api.md): what the resume choice needs to start
on, and how many jobs use each stored file."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.search.application.resume_choice import clear_file_uses
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.pipeline_settings_repo import PipelineSettingsRepo


@dataclass(frozen=True)
class PipelineApiDeps:
    sessions: async_sessionmaker[AsyncSession]


class ResumeUsageOut(BaseModel):
    resume_file_id: UUID
    jobs: int


class PipelineResumesOut(BaseModel):
    last_choice: UUID | None
    usage: list[ResumeUsageOut]


def create_pipeline_router(deps: PipelineApiDeps) -> APIRouter:
    router = APIRouter(prefix="/pipeline", tags=["pipeline"])

    @router.get("/resumes", response_model=PipelineResumesOut)
    async def pipeline_resumes() -> PipelineResumesOut:
        """The resume the person chose the last time they marked a job (the choice starts on it),
        and how many pipeline jobs use each stored file."""
        async with deps.sessions() as session:
            last = await PipelineSettingsRepo(session).last_choice()
            usage = await InterviewsRepo(session).usage()
        return PipelineResumesOut(
            last_choice=last,
            usage=[ResumeUsageOut(resume_file_id=f, jobs=n) for f, n in sorted(usage.items())],
        )

    @router.delete("/resumes/{file_id}/uses", status_code=204)
    async def clear_uses(file_id: UUID) -> Response:
        """Forget a stored file on every job and as the last choice, names included. Used before
        the file is removed when the person wants nothing of it left (feature 002f, FR-009)."""
        async with deps.sessions() as session:
            await clear_file_uses(InterviewsRepo(session), PipelineSettingsRepo(session), file_id)
            await session.commit()
        return Response(status_code=204)

    return router
