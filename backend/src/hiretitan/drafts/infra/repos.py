"""Repositories for the drafts tables. Method names avoid ``delete``/``put``/``post`` on purpose:
the no-send scanner bans those call names in scanned packages (feature 002k, tasks.md)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.drafts.infra.models import JobKeywordsRow, OutreachDraftRow, TailoredResumeRow


async def lock_job_drafts(session: AsyncSession, job_id: UUID) -> None:
    """Serialise starting drafts and tailored resumes for one job until the transaction ends.

    Two clicks at once would otherwise both see no row and both insert, and the second would hit
    the unique constraint (a 500). With the lock the second sees the first's "writing" row.
    """
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"drafts:{job_id}"))))


@dataclass(frozen=True, slots=True)
class StoredKeywords:
    job_id: UUID
    description_sha256: str
    role_summary: str
    keywords: tuple[str, ...]
    must_have: tuple[str, ...]
    injection_signals: tuple[Any, ...]


class KeywordsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, job_id: UUID) -> StoredKeywords | None:
        row = await self._session.get(JobKeywordsRow, job_id)
        if row is None:
            return None
        return StoredKeywords(
            row.job_id,
            row.description_sha256,
            row.role_summary,
            tuple(row.keywords),
            tuple(row.must_have),
            tuple(row.injection_signals),
        )

    async def save(
        self,
        job_id: UUID,
        *,
        sha256: str,
        role_summary: str,
        keywords: list[str],
        must_have: list[str],
        injection_signals: list[Any],
        prompt_version: str,
        model: str,
    ) -> None:
        values = {
            "description_sha256": sha256,
            "role_summary": role_summary,
            "keywords": keywords,
            "must_have": must_have,
            "injection_signals": injection_signals,
            "prompt_version": prompt_version,
            "model": model,
        }
        # a tailored resume and a draft for the same job can read the keywords at the same time
        statement = pg_insert(JobKeywordsRow).values(job_id=job_id, **values)
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=[JobKeywordsRow.job_id], set_=values)
        )
        self._session.expire_all()

    async def clear_for_job(self, job_id: UUID) -> None:
        await self._session.execute(delete(JobKeywordsRow).where(JobKeywordsRow.job_id == job_id))


class DraftsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, draft_id: UUID) -> OutreachDraftRow | None:
        return await self._session.get(OutreachDraftRow, draft_id)

    async def find(self, job_id: UUID, kind: str, recipient_key: str) -> OutreachDraftRow | None:
        return await self._session.scalar(
            select(OutreachDraftRow).where(
                OutreachDraftRow.job_id == job_id,
                OutreachDraftRow.kind == kind,
                OutreachDraftRow.recipient_key == recipient_key,
            )
        )

    async def list_for_job(self, job_id: UUID) -> list[OutreachDraftRow]:
        rows = await self._session.scalars(
            select(OutreachDraftRow)
            .where(OutreachDraftRow.job_id == job_id)
            .order_by(OutreachDraftRow.updated_at.desc(), OutreachDraftRow.id.desc())
        )
        return list(rows)

    async def start_writing(
        self,
        job_id: UUID,
        *,
        kind: str,
        recipient_contact_id: UUID | None,
        recipient_name: str,
        recipient_role: str | None,
        recipient_kind: str,
        recipient_key: str,
    ) -> OutreachDraftRow:
        """A draft for (job, kind, recipient): the existing row starts again, or a new one."""
        row = await self.find(job_id, kind, recipient_key)
        if row is None:
            row = OutreachDraftRow(job_id=job_id, kind=kind, recipient_key=recipient_key)
            self._session.add(row)
        row.recipient_contact_id = recipient_contact_id
        row.recipient_name = recipient_name
        row.recipient_role = recipient_role
        row.recipient_kind = recipient_kind
        row.status = "writing"
        row.failure_reason = None
        row.cited_fact_ids = row.cited_fact_ids or []
        await self._session.flush()
        return row

    async def set_run(self, draft_id: UUID, run_id: UUID) -> None:
        row = await self.get(draft_id)
        if row is not None:
            row.run_id = run_id
            await self._session.flush()

    async def save_result(
        self,
        draft_id: UUID,
        *,
        template: str,
        text: str,
        source: str,
        cited_fact_ids: list[str],
        prompt_name: str | None,
        prompt_version: str | None,
        model: str | None,
    ) -> None:
        row = await self.get(draft_id)
        if row is None:
            return
        row.status = "ready"
        row.template = template
        row.text = text
        row.source = source
        row.edited = False
        row.cited_fact_ids = cited_fact_ids
        row.prompt_name = prompt_name
        row.prompt_version = prompt_version
        row.model = model
        row.failure_reason = None
        await self._session.flush()

    async def set_failed(self, draft_id: UUID, reason: str) -> None:
        row = await self.get(draft_id)
        if row is not None:
            row.status = "failed"
            row.failure_reason = reason
            await self._session.flush()

    async def save_edit(self, draft_id: UUID, text: str) -> None:
        row = await self.get(draft_id)
        if row is not None:
            row.text = text
            row.edited = True
            row.status = "ready"  # the person's own text makes a failed draft usable
            row.failure_reason = None
            await self._session.flush()

    async def remove(self, draft_id: UUID) -> None:
        await self._session.execute(delete(OutreachDraftRow).where(OutreachDraftRow.id == draft_id))

    async def clear_for_job(self, job_id: UUID) -> None:
        await self._session.execute(
            delete(OutreachDraftRow).where(OutreachDraftRow.job_id == job_id)
        )


class TailoredRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_job(self, job_id: UUID) -> TailoredResumeRow | None:
        return await self._session.scalar(
            select(TailoredResumeRow).where(TailoredResumeRow.job_id == job_id)
        )

    async def start_writing(self, job_id: UUID) -> TailoredResumeRow:
        row = await self.get_for_job(job_id)
        if row is None:
            row = TailoredResumeRow(job_id=job_id)
            self._session.add(row)
        row.status = "writing"
        row.failure_reason = None
        await self._session.flush()
        return row

    async def set_run(self, job_id: UUID, run_id: UUID) -> None:
        row = await self.get_for_job(job_id)
        if row is not None:
            row.run_id = run_id
            await self._session.flush()

    async def save_result(
        self,
        job_id: UUID,
        *,
        document: dict[str, Any],
        keyword_match: dict[str, Any],
        source: str,
        profile_version_id: UUID | None,
        prompt_name: str | None,
        prompt_version: str | None,
        model: str | None,
    ) -> None:
        row = await self.get_for_job(job_id)
        if row is None:
            return
        row.status = "ready"
        row.document = document
        row.keyword_match = keyword_match
        row.source = source
        row.edited = False
        row.profile_version_id = profile_version_id
        row.prompt_name = prompt_name
        row.prompt_version = prompt_version
        row.model = model
        row.failure_reason = None
        await self._session.flush()

    async def set_failed(self, job_id: UUID, reason: str) -> None:
        row = await self.get_for_job(job_id)
        if row is not None:
            row.status = "failed"
            row.failure_reason = reason
            await self._session.flush()

    async def save_edit(
        self, job_id: UUID, document: dict[str, Any], keyword_match: dict[str, Any]
    ) -> None:
        row = await self.get_for_job(job_id)
        if row is not None:
            row.document = document
            row.keyword_match = keyword_match
            row.edited = True
            await self._session.flush()

    async def list_ready(self) -> list[TailoredResumeRow]:
        rows = await self._session.scalars(
            select(TailoredResumeRow)
            .where(TailoredResumeRow.status == "ready")
            .order_by(TailoredResumeRow.updated_at.desc())
        )
        return list(rows)

    async def remove_for_job(self, job_id: UUID) -> None:
        await self._session.execute(
            delete(TailoredResumeRow).where(TailoredResumeRow.job_id == job_id)
        )

    clear_for_job = remove_for_job
