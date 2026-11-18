"""Outreach draft endpoints (contracts/rest-api.md, "Recipients" and "Outreach drafts").

Drafts are text for the person to copy. Nothing here, or anywhere in the app, sends them
(constitution I).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.drafts.application.ports import (
    ConfirmedProfile,
    ContactLookup,
    JobInfo,
    JobSource,
    ProfileFactsSource,
)
from hiretitan.drafts.domain.facts import drafting_facts
from hiretitan.drafts.domain.recipient import (
    KINDS,
    RecipientKind,
    clean_typed,
    kind_from_role,
    recipient_key,
)
from hiretitan.drafts.domain.resume_doc import strip_control
from hiretitan.drafts.infra.models import OutreachDraftRow
from hiretitan.drafts.infra.repos import DraftsRepo, KeywordsRepo, lock_job_drafts
from hiretitan.drafts.workflow.outreach import OUTREACH_WORKFLOW
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.llm.provider_status import MESSAGES
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.runtime.runner import RunQueue
from hiretitan.platform.web.problems import ProblemError

CONNECTION_LIMIT = 200
TEXT_MAX = 2000
UNAVAILABLE = ("missing", "rejected", "out_of_credit")
PAUSE_TO_STATUS = {
    "key_missing": "missing",
    "key_rejected": "rejected",
    "out_of_credit": "out_of_credit",
}


@dataclass(frozen=True)
class DraftsApiDeps:
    sessions: async_sessionmaker[AsyncSession]
    queue: RunQueue
    jobs: JobSource
    profile: ProfileFactsSource
    contacts: ContactLookup
    provider: str = "openai"


class RecipientContactOut(BaseModel):
    contact_id: UUID
    name: str
    role: str | None
    kind: RecipientKind


class RecipientsOut(BaseModel):
    contacts: list[RecipientContactOut]
    kinds: list[RecipientKind]


class RecipientOut(BaseModel):
    contact_id: UUID | None
    name: str
    role: str | None
    kind: RecipientKind


class CitedFactOut(BaseModel):
    id: str
    text: str


class SignalOut(BaseModel):
    rule_id: str
    severity: str
    excerpt: str


class DraftOut(BaseModel):
    id: UUID
    kind: Literal["connection_request", "referral_message"]
    recipient: RecipientOut
    status: Literal["writing", "ready", "failed"]
    paused_reason: str | None
    text: str | None
    source: Literal["ai", "fallback"] | None
    edited: bool
    cited_facts: list[CitedFactOut]
    failure_reason: str | None
    chars: int
    over_limit: bool
    updated_at: datetime


class DraftsOut(BaseModel):
    drafts: list[DraftOut]
    injection_signals: list[SignalOut]


class RecipientIn(BaseModel):
    contact_id: UUID | None = None
    name: str | None = Field(default=None, max_length=400)
    role: str | None = Field(default=None, max_length=400)


class DraftIn(BaseModel):
    kind: Literal["connection_request", "referral_message"]
    recipient: RecipientIn
    recipient_kind: RecipientKind | None = None
    regenerate: bool = False


class DraftStarted(BaseModel):
    id: UUID
    status: Literal["writing"]


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=TEXT_MAX)


def _not_found(what: str = "job") -> ProblemError:
    return ProblemError(404, f"That {what} was not found.")


def injection_signals(stored: tuple[Any, ...]) -> list[SignalOut]:
    return [
        SignalOut(
            rule_id=str(s.get("rule_id", "")),
            severity=str(s.get("severity", "")),
            excerpt=str(s.get("excerpt", ""))[:200],
        )
        for s in stored
        if isinstance(s, dict)
    ]


async def paused_message(session: AsyncSession, provider: str, run_id: UUID | None) -> str | None:
    """Why a waiting draft is paused, in the provider's own words, when its run is paused."""
    if run_id is None:
        return None
    run = await RunsRepo(session).get(run_id)
    if run is None or run.state.status is not RunStatus.paused or run.state.pause_reason is None:
        return None
    status = PAUSE_TO_STATUS.get(run.state.pause_reason.value)
    stored = await ProviderStatusRepo(session).get(provider)
    if stored is not None and stored.message:
        return stored.message
    return MESSAGES.get(status or "") or "The AI is not available right now."


async def require_ai(session: AsyncSession, provider: str) -> None:
    """Refuse to start AI work when the provider is known to be down (spec FR-007)."""
    stored = await ProviderStatusRepo(session).get(provider)
    if stored is not None and stored.status in UNAVAILABLE:
        message = stored.message or MESSAGES.get(stored.status) or "The AI is not available."
        raise ProblemError(409, message, reason="ai_unavailable")


def create_drafts_router(deps: DraftsApiDeps) -> APIRouter:
    router = APIRouter(tags=["drafts"])

    async def load_job(job_id: UUID) -> JobInfo:
        job = await deps.jobs.get(job_id)
        if job is None:
            raise _not_found()
        return job

    async def to_out(
        session: AsyncSession, row: OutreachDraftRow, profile: ConfirmedProfile | None
    ) -> DraftOut:
        by_id = {f.id: f.text for f in drafting_facts(profile.view)} if profile else {}
        cited = [CitedFactOut(id=i, text=by_id[i]) for i in row.cited_fact_ids if i in by_id]
        paused = (
            await paused_message(session, deps.provider, row.run_id)
            if row.status == "writing"
            else None
        )
        text = row.text
        return DraftOut(
            id=row.id,
            kind=row.kind,
            recipient=RecipientOut(
                contact_id=row.recipient_contact_id,
                name=row.recipient_name,
                role=row.recipient_role,
                kind=row.recipient_kind,
            ),
            status=row.status,
            paused_reason=paused,
            text=text,
            source=row.source,
            edited=row.edited,
            cited_facts=cited,
            failure_reason=row.failure_reason,
            chars=len(text) if text else 0,
            over_limit=row.kind == "connection_request" and len(text or "") > CONNECTION_LIMIT,
            updated_at=row.updated_at,
        )

    @router.get("/jobs/{job_id}/recipients", response_model=RecipientsOut)
    async def recipients(job_id: UUID) -> RecipientsOut:
        job = await load_job(job_id)
        people = await deps.contacts.for_company(job.company_id) if job.company_id else []
        return RecipientsOut(
            contacts=[
                RecipientContactOut(
                    contact_id=c.id, name=c.name, role=c.role, kind=kind_from_role(c.role)
                )
                for c in people
            ],
            kinds=list(KINDS),
        )

    @router.get("/jobs/{job_id}/drafts", response_model=DraftsOut)
    async def list_drafts(job_id: UUID) -> DraftsOut:
        await load_job(job_id)
        profile = await deps.profile.current()
        async with deps.sessions() as session:
            rows = await DraftsRepo(session).list_for_job(job_id)
            stored = await KeywordsRepo(session).get(job_id)
            out = [await to_out(session, row, profile) for row in rows]
        signals = injection_signals(stored.injection_signals) if stored else []
        return DraftsOut(drafts=out, injection_signals=signals)

    @router.post("/jobs/{job_id}/drafts", response_model=None, status_code=202)
    async def create_draft(job_id: UUID, body: DraftIn, response: Response) -> Any:
        job = await load_job(job_id)
        contact_id: UUID | None = None
        if body.recipient.contact_id is not None:
            contact = await deps.contacts.get(body.recipient.contact_id)
            if contact is None or job.company_id is None or contact.company_id != job.company_id:
                raise _not_found("contact")
            contact_id, name, role = contact.id, contact.name, contact.role
        else:
            try:
                typed = clean_typed(body.recipient.name or "", body.recipient.role)
            except ValueError as error:
                raise ProblemError(422, str(error)) from error
            name, role = typed.name, typed.role
        kind: RecipientKind = body.recipient_kind or kind_from_role(role)
        key = recipient_key(contact_id, name)
        profile = await deps.profile.current()
        async with deps.sessions() as session:
            repo = DraftsRepo(session)
            await lock_job_drafts(session, job_id)
            existing = await repo.find(job_id, body.kind, key)
            if existing is not None and existing.status == "writing":
                raise ProblemError(
                    409, "This draft is still being written.", reason="draft_in_progress"
                )
            if existing is not None and existing.status == "ready" and not body.regenerate:
                response.status_code = 200
                return await to_out(session, existing, profile)
            if profile is None:
                raise ProblemError(
                    409,
                    "Finish your profile first, then write a draft.",
                    reason="no_confirmed_profile",
                )
            await require_ai(session, deps.provider)
            row = await repo.start_writing(
                job_id,
                kind=body.kind,
                recipient_contact_id=contact_id,
                recipient_name=name,
                recipient_role=role,
                recipient_kind=kind,
                recipient_key=key,
            )
            run = await RunsRepo(session).create(OUTREACH_WORKFLOW, subject_id=row.id)
            await repo.set_run(row.id, run.id)
            await session.commit()
            draft_id = row.id
        await deps.queue.enqueue(run.id)
        return DraftStarted(id=draft_id, status="writing")

    async def load_draft(session: AsyncSession, draft_id: UUID) -> OutreachDraftRow:
        row = await DraftsRepo(session).get(draft_id)
        if row is None:
            raise _not_found("draft")
        return row

    @router.put("/drafts/{draft_id}", response_model=DraftOut)
    async def edit_draft(draft_id: UUID, body: TextIn) -> DraftOut:
        profile = await deps.profile.current()
        async with deps.sessions() as session:
            row = await load_draft(session, draft_id)
            if row.status == "writing":
                raise ProblemError(
                    409, "This draft is still being written.", reason="draft_in_progress"
                )
            await DraftsRepo(session).save_edit(draft_id, strip_control(body.text))
            await session.commit()
            saved = await load_draft(session, draft_id)
            await session.refresh(saved)  # the server set updated_at
            return await to_out(session, saved, profile)

    @router.delete("/drafts/{draft_id}", status_code=204)
    async def remove_draft(draft_id: UUID) -> Response:
        async with deps.sessions() as session:
            await load_draft(session, draft_id)
            await DraftsRepo(session).remove(draft_id)
            await session.commit()
        return Response(status_code=204)

    return router
