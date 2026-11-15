"""Pipeline endpoints (feature 002f, contracts/rest-api.md): what the resume choice needs to start
on, and how many jobs use each stored file."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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

    return router
