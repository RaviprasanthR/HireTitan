"""Tailored resume endpoints (contracts/rest-api.md, "Tailored resume").

The resume is built from the confirmed profile only and downloaded by the person; nothing is sent.
"""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, ValidationError

from hiretitan.drafts.api.drafts import (
    DraftsApiDeps,
    SignalOut,
    injection_signals,
    paused_message,
    require_ai,
)
from hiretitan.drafts.domain.keywords import backed, match
from hiretitan.drafts.domain.resume_doc import ResumeDocument, document_from_dict, document_text
from hiretitan.drafts.infra.models import DOCUMENT_MAX_BYTES, TailoredResumeRow
from hiretitan.drafts.infra.render.docx import render_docx
from hiretitan.drafts.infra.render.pdf import render_pdf
from hiretitan.drafts.infra.repos import KeywordsRepo, TailoredRepo, lock_job_drafts
from hiretitan.drafts.workflow.tailor import DESCRIPTION_MIN, TAILOR_WORKFLOW
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.web.problems import ProblemError

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_UNSAFE = re.compile(r"[^A-Za-z0-9 ._-]+")


class MissingOut(BaseModel):
    keyword: str
    reason: Literal["not_in_profile", "not_in_resume"]


class KeywordMatchOut(BaseModel):
    matched: list[str]
    missing: list[MissingOut]
    score: float


class TailoredOut(BaseModel):
    id: UUID
    status: Literal["writing", "ready", "failed"]
    paused_reason: str | None
    document: ResumeDocument | None
    keyword_match: KeywordMatchOut | None
    source: Literal["ai", "fallback"] | None
    edited: bool
    failure_reason: str | None
    injection_signals: list[SignalOut]
    updated_at: datetime


class TailorIn(BaseModel):
    regenerate: bool = False


class TailorStarted(BaseModel):
    job_id: UUID
    status: Literal["writing"]


class DocumentIn(BaseModel):
    document: dict[str, Any]


class TailoredListItem(BaseModel):
    job_id: UUID
    job_title: str
    company: str
    updated_at: datetime
    source: Literal["ai", "fallback"] | None
    edited: bool


def safe_filename(*parts: str) -> str:
    """A download name made of plain characters only, whatever the person or job is called."""
    joined = " - ".join(p for p in parts if p)
    ascii_only = unicodedata.normalize("NFKD", joined).encode("ascii", "ignore").decode()
    cleaned = " ".join(_UNSAFE.sub(" ", ascii_only).split()).strip(" .-")
    return (cleaned or "resume")[:100]


async def start_tailor(
    deps: DraftsApiDeps, job_id: UUID, regenerate: bool = False
) -> TailorStarted | TailoredResumeRow:
    """Start tailoring the resume for a job (or return the ready one when not asked to redo it).

    Shared by the endpoint and Mikasa's actions (002m). Raises ``ProblemError``.
    """
    job = await deps.jobs.get(job_id)
    if job is None:
        raise ProblemError(404, "That job was not found.")
    profile = await deps.profile.current()
    async with deps.sessions() as session:
        repo = TailoredRepo(session)
        await lock_job_drafts(session, job_id)
        current = await repo.get_for_job(job_id)
        if current is not None and current.status == "writing":
            raise ProblemError(
                409, "This resume is still being written.", reason="resume_in_progress"
            )
        if current is not None and current.status == "ready" and not regenerate:
            return current
        if len(job.description.strip()) < DESCRIPTION_MIN:
            raise ProblemError(
                409,
                "This job has no description yet. Add it, then tailor the resume.",
                reason="no_description",
            )
        if profile is None:
            raise ProblemError(
                409,
                "Finish your profile first, then tailor a resume.",
                reason="no_confirmed_profile",
            )
        await require_ai(session, deps.provider)
        await repo.start_writing(job_id)
        run = await RunsRepo(session).create(TAILOR_WORKFLOW, subject_id=job_id)
        await repo.set_run(job_id, run.id)
        await session.commit()
    await deps.queue.enqueue(run.id)
    return TailorStarted(job_id=job_id, status="writing")


def create_resumes_router(deps: DraftsApiDeps) -> APIRouter:
    router = APIRouter(tags=["tailored-resumes"])

    async def row_out(session: Any, row: TailoredResumeRow, job_id: UUID) -> TailoredOut:
        stored = await KeywordsRepo(session).get(job_id)
        paused = (
            await paused_message(session, deps.provider, row.run_id)
            if row.status == "writing"
            else None
        )
        return TailoredOut(
            id=row.id,
            status=row.status,
            paused_reason=paused,
            document=ResumeDocument.model_validate(row.document) if row.document else None,
            keyword_match=KeywordMatchOut.model_validate(row.keyword_match)
            if row.keyword_match
            else None,
            source=row.source,
            edited=row.edited,
            failure_reason=row.failure_reason,
            injection_signals=injection_signals(stored.injection_signals) if stored else [],
            updated_at=row.updated_at,
        )

    async def existing(session: Any, job_id: UUID) -> TailoredResumeRow:
        row = await TailoredRepo(session).get_for_job(job_id)
        if row is None:
            raise ProblemError(404, "No tailored resume for this job.", reason="not_tailored")
        return row

    async def live_job(job_id: UUID) -> None:
        if await deps.jobs.get(job_id) is None:
            raise ProblemError(404, "That job was not found.")

    @router.get("/jobs/{job_id}/tailored-resume", response_model=TailoredOut)
    async def get_resume(job_id: UUID) -> TailoredOut:
        await live_job(job_id)
        async with deps.sessions() as session:
            return await row_out(session, await existing(session, job_id), job_id)

    @router.post("/jobs/{job_id}/tailored-resume", response_model=None, status_code=202)
    async def start_resume(job_id: UUID, body: TailorIn, response: Response) -> Any:
        started = await start_tailor(deps, job_id, body.regenerate)
        if isinstance(started, TailorStarted):
            return started
        response.status_code = 200
        async with deps.sessions() as session:
            return await row_out(session, started, job_id)

    @router.put("/jobs/{job_id}/tailored-resume", response_model=TailoredOut)
    async def save_resume(job_id: UUID, body: DocumentIn) -> TailoredOut:
        await live_job(job_id)
        try:
            doc = document_from_dict(body.document)
        except ValidationError as error:
            raise ProblemError(422, "The resume has a value that is not allowed.") from error
        dumped = doc.model_dump(mode="json")
        if len(json.dumps(dumped).encode("utf-8")) > DOCUMENT_MAX_BYTES - 1024:
            raise ProblemError(422, "The resume is too long.")
        profile = await deps.profile.current()
        async with deps.sessions() as session:
            row = await existing(session, job_id)
            if row.status == "writing":
                raise ProblemError(
                    409, "This resume is still being written.", reason="resume_in_progress"
                )
            stored = await KeywordsRepo(session).get(job_id)
            wanted = list(dict.fromkeys([*stored.must_have, *stored.keywords])) if stored else []
            result = match(
                wanted, document_text(doc), backed(wanted, profile.view) if profile else set()
            )
            await TailoredRepo(session).save_edit(job_id, dumped, result.to_dict())
            await session.commit()
            saved = await existing(session, job_id)
            await session.refresh(saved)
            return await row_out(session, saved, job_id)

    @router.delete("/jobs/{job_id}/tailored-resume", status_code=204)
    async def remove_resume(job_id: UUID) -> Response:
        async with deps.sessions() as session:
            row = await existing(session, job_id)
            if row.status == "writing":
                raise ProblemError(
                    409, "This resume is still being written.", reason="resume_in_progress"
                )
            await TailoredRepo(session).remove_for_job(job_id)
            await session.commit()
        return Response(status_code=204)

    async def download(job_id: UUID, extension: str) -> Response:
        job = await deps.jobs.get(job_id)
        if job is None:
            raise ProblemError(404, "That job was not found.")
        async with deps.sessions() as session:
            row = await TailoredRepo(session).get_for_job(job_id)
        if row is None or row.status != "ready" or not row.document:
            raise ProblemError(404, "No tailored resume for this job.", reason="not_tailored")
        doc = document_from_dict(row.document)
        name = safe_filename(doc.contact.name, job.company_name, job.title)
        render = render_pdf if extension == "pdf" else render_docx
        data = await asyncio.to_thread(render, doc)  # CPU work, kept off the event loop
        return Response(
            content=data,
            media_type=PDF if extension == "pdf" else DOCX,
            headers={"Content-Disposition": f'attachment; filename="{name}.{extension}"'},
        )

    @router.get("/jobs/{job_id}/tailored-resume.pdf")
    async def download_pdf(job_id: UUID) -> Response:
        return await download(job_id, "pdf")

    @router.get("/jobs/{job_id}/tailored-resume.docx")
    async def download_docx(job_id: UUID) -> Response:
        return await download(job_id, "docx")

    @router.get("/tailored-resumes", response_model=list[TailoredListItem])
    async def list_resumes() -> list[TailoredListItem]:
        async with deps.sessions() as session:
            rows = await TailoredRepo(session).list_ready()
        items: list[TailoredListItem] = []
        for row in rows:
            job = await deps.jobs.get(row.job_id)
            if job is None:
                continue
            items.append(
                TailoredListItem(
                    job_id=row.job_id,
                    job_title=job.title,
                    company=job.company_name,
                    updated_at=row.updated_at,
                    source=row.source,
                    edited=row.edited,
                )
            )
        return items

    return router
