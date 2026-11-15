"""The person's own interview notes in the database (feature 002e).

Kept apart from the other repositories so an import-linter contract can forbid every AI path
(workflow, prompts, LLM platform) from importing it: these notes never reach a model (FR-010).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.domain.interviews import RoundSummary, status_summary
from hiretitan.search.domain.resume_choice import ResumeChoice, choice_from
from hiretitan.search.infra.models import (
    InterviewQuestionRow,
    InterviewRoundRow,
    JobRow,
    PipelineDetailsRow,
)


@dataclass(frozen=True, slots=True)
class RoundData:
    round: InterviewRoundRow
    questions: list[InterviewQuestionRow]


@dataclass(frozen=True, slots=True)
class InterviewData:
    details: PipelineDetailsRow | None
    rounds: list[RoundData]


ROUND_FIELDS = ("kind", "scheduled_at", "interviewers", "state", "feedback")
QUESTION_FIELDS = ("question", "answer")


class InterviewsRepo:
    """The contact, source, rounds and questions of pipeline jobs. The person's own data, never
    read by a workflow or a prompt (feature 002e, FR-010)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # contact and source (one row per job, dropped when it holds nothing)

    async def _details_row(self, job_id: UUID) -> PipelineDetailsRow:
        # Two saves of a fresh job (contact and source) can arrive together: the insert must not
        # fail for the one that comes second.
        await self._session.execute(
            pg_insert(PipelineDetailsRow)
            .values(job_id=job_id)
            .on_conflict_do_nothing(index_elements=[PipelineDetailsRow.job_id])
        )
        return await self._session.get_one(PipelineDetailsRow, job_id, populate_existing=True)

    async def _prune(self, job_id: UUID) -> None:
        row = await self._session.get(PipelineDetailsRow, job_id, populate_existing=True)
        if (
            row is not None
            and row.contact_name is None
            and row.source is None
            and row.resume_name is None
        ):
            await self._session.execute(
                delete(PipelineDetailsRow).where(PipelineDetailsRow.job_id == job_id)
            )
            self._session.expunge(row)
        await self._session.flush()

    async def upsert_contact(self, job_id: UUID, fields: ContactFields) -> None:
        """Replace every contact field (an empty optional field clears it)."""
        row = await self._details_row(job_id)
        row.contact_name = fields.name
        row.contact_role = fields.role
        row.contact_email = fields.email
        row.contact_phone = fields.phone
        row.contact_linkedin = fields.linkedin_url
        await self._session.flush()

    async def clear_contact(self, job_id: UUID) -> None:
        row = await self._session.get(PipelineDetailsRow, job_id)
        if row is None:
            return
        row.contact_name = row.contact_role = row.contact_email = None
        row.contact_phone = row.contact_linkedin = None
        await self._prune(job_id)

    async def set_source(self, job_id: UUID, kind: str | None, firm_name: str | None) -> None:
        row = await self._details_row(job_id)
        row.source = kind
        row.firm_name = firm_name
        await self._session.flush()
        await self._prune(job_id)

    # the resume used (feature 002f)

    async def set_resume(self, job_id: UUID, file_id: UUID, name: str, added_on: date) -> None:
        """Record a stored file as the job's resume: the link, and a copy of its name and the day
        it was added, so the name stays as a note if the file is removed later."""
        row = await self._details_row(job_id)
        row.resume_file_id = file_id
        row.resume_name = name
        row.resume_added_on = added_on
        await self._session.flush()

    async def clear_resume(self, job_id: UUID) -> None:
        """Forget the job's resume, or its removed-file note; drop the row if nothing is left."""
        row = await self._session.get(PipelineDetailsRow, job_id, populate_existing=True)
        if row is None:
            return
        row.resume_file_id = row.resume_name = row.resume_added_on = None
        await self._prune(job_id)

    async def resume_choices(self, job_ids: list[UUID]) -> dict[UUID, ResumeChoice]:
        """The resume shown for each of these jobs that has one (chosen, or a removed note), in
        one query; a job missing from the answer has none."""
        if not job_ids:
            return {}
        rows = await self._session.execute(
            select(
                PipelineDetailsRow.job_id,
                PipelineDetailsRow.resume_file_id,
                PipelineDetailsRow.resume_name,
                PipelineDetailsRow.resume_added_on,
            ).where(
                PipelineDetailsRow.job_id.in_(job_ids), PipelineDetailsRow.resume_name.is_not(None)
            )
        )
        return {job_id: choice_from(file_id, name, day) for job_id, file_id, name, day in rows}

    async def usage(self) -> dict[UUID, int]:
        """How many jobs point at each stored file (a removed note points at none)."""
        rows = await self._session.execute(
            select(PipelineDetailsRow.resume_file_id, func.count())
            .where(PipelineDetailsRow.resume_file_id.is_not(None))
            .group_by(PipelineDetailsRow.resume_file_id)
        )
        return {file_id: count for file_id, count in rows if file_id is not None}

    # reading

    async def details(self, job_id: UUID) -> InterviewData:
        row = await self._session.get(PipelineDetailsRow, job_id)
        rounds = (
            await self._session.execute(
                select(InterviewRoundRow)
                .where(InterviewRoundRow.job_id == job_id)
                .order_by(InterviewRoundRow.number)
            )
        ).scalars()
        round_rows = list(rounds)
        by_round: dict[UUID, list[InterviewQuestionRow]] = {r.id: [] for r in round_rows}
        if round_rows:
            questions = await self._session.execute(
                select(InterviewQuestionRow)
                .where(InterviewQuestionRow.round_id.in_(list(by_round)))
                .order_by(InterviewQuestionRow.position, InterviewQuestionRow.id)
            )
            for question in questions.scalars():
                by_round[question.round_id].append(question)
        return InterviewData(row, [RoundData(r, by_round[r.id]) for r in round_rows])

    async def lock_job(self, job_id: UUID) -> None:
        """Hold the job row until the transaction ends, so a check and the write that follows it
        (the failed-round rule, the pipeline state) cannot be separated by another request."""
        await self._session.execute(select(JobRow.id).where(JobRow.id == job_id).with_for_update())

    async def get_round(self, round_id: UUID) -> InterviewRoundRow | None:
        # always from the database: a row seen before a lock may have been removed since
        return await self._session.get(InterviewRoundRow, round_id, populate_existing=True)

    async def get_question(self, question_id: UUID) -> InterviewQuestionRow | None:
        return await self._session.get(InterviewQuestionRow, question_id, populate_existing=True)

    # rounds

    async def add_round(
        self,
        job_id: UUID,
        *,
        kind: str,
        scheduled_at: datetime | None = None,
        interviewers: str | None = None,
    ) -> InterviewRoundRow:
        """The next number of the job (the highest plus one) and the state ``scheduled``."""
        # the job row is locked so two adds at once are numbered one after the other
        await self._session.execute(select(JobRow.id).where(JobRow.id == job_id).with_for_update())
        top = (
            await self._session.execute(
                select(func.max(InterviewRoundRow.number)).where(InterviewRoundRow.job_id == job_id)
            )
        ).scalar()
        row = InterviewRoundRow(
            job_id=job_id,
            number=(top or 0) + 1,
            kind=kind,
            scheduled_at=scheduled_at,
            interviewers=interviewers,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def update_round(self, round_id: UUID, changes: dict[str, Any]) -> InterviewRoundRow:
        row = await self._session.get_one(InterviewRoundRow, round_id)
        for name, value in changes.items():
            if name not in ROUND_FIELDS:
                raise ValueError(f"A round has no field {name!r}.")
            setattr(row, name, value)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def delete_round(self, round_id: UUID) -> None:
        await self._session.execute(
            delete(InterviewRoundRow).where(InterviewRoundRow.id == round_id)
        )
        await self._session.flush()

    # questions

    async def add_question(
        self, round_id: UUID, question: str, answer: str | None
    ) -> InterviewQuestionRow:
        await self._session.execute(
            select(InterviewRoundRow.id).where(InterviewRoundRow.id == round_id).with_for_update()
        )
        top = (
            await self._session.execute(
                select(func.max(InterviewQuestionRow.position)).where(
                    InterviewQuestionRow.round_id == round_id
                )
            )
        ).scalar()
        row = InterviewQuestionRow(
            round_id=round_id, position=(top or 0) + 1, question=question, answer=answer
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def update_question(
        self, question_id: UUID, changes: dict[str, Any]
    ) -> InterviewQuestionRow:
        row = await self._session.get_one(InterviewQuestionRow, question_id)
        for name, value in changes.items():
            if name not in QUESTION_FIELDS:
                raise ValueError(f"A question has no field {name!r}.")
            setattr(row, name, value)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def delete_question(self, question_id: UUID) -> None:
        await self._session.execute(
            delete(InterviewQuestionRow).where(InterviewQuestionRow.id == question_id)
        )
        await self._session.flush()

    # the job as a whole

    async def delete_for_job(self, job_id: UUID) -> None:
        """Everything recorded for the job (a deleted job keeps its row, so no cascade fires)."""
        await self._session.execute(
            delete(InterviewRoundRow).where(InterviewRoundRow.job_id == job_id)
        )
        await self._session.execute(
            delete(PipelineDetailsRow).where(PipelineDetailsRow.job_id == job_id)
        )
        await self._session.flush()

    async def merge_details(self, keep_id: UUID, loser_id: UUID) -> None:
        """Fold the losing job's notes into the kept job (feature 002e, research R7): the kept
        job's own contact, source and resume stay, and the loser's fill them only when empty; the
        loser's rounds come over (renumbered 1..n, questions with them) only when the kept job
        has none. Whatever is left of the loser's notes is removed."""
        # one order for both rows, so two merges at once cannot wait on each other
        for job_id in sorted((keep_id, loser_id)):
            await self.lock_job(job_id)
        lost = await self._session.get(PipelineDetailsRow, loser_id, populate_existing=True)
        if lost is not None and (
            lost.contact_name is not None or lost.source is not None or lost.resume_name is not None
        ):
            kept = await self._details_row(keep_id)
            if kept.contact_name is None and lost.contact_name is not None:
                kept.contact_name = lost.contact_name
                kept.contact_role = lost.contact_role
                kept.contact_email = lost.contact_email
                kept.contact_phone = lost.contact_phone
                kept.contact_linkedin = lost.contact_linkedin
            if kept.source is None and lost.source is not None:
                kept.source = lost.source
                kept.firm_name = lost.firm_name
            if kept.resume_name is None and lost.resume_name is not None:
                # the link, the name and the day come together (a check requires it); a removed
                # file's note comes over as it is, with no link (feature 002f, FR-010)
                kept.resume_file_id = lost.resume_file_id
                kept.resume_name = lost.resume_name
                kept.resume_added_on = lost.resume_added_on
            await self._session.flush()
        has_rounds = await self._session.scalar(
            select(func.count())
            .select_from(InterviewRoundRow)
            .where(InterviewRoundRow.job_id == keep_id)
        )
        if not has_rounds:
            moving = (
                await self._session.scalars(
                    select(InterviewRoundRow)
                    .where(InterviewRoundRow.job_id == loser_id)
                    .order_by(InterviewRoundRow.number)
                )
            ).all()
            for position, row in enumerate(moving, start=1):
                row.job_id = keep_id
                row.number = position
            await self._session.flush()
        await self.delete_for_job(loser_id)
        await self._prune(keep_id)

    async def summaries(self, job_ids: list[UUID]) -> dict[UUID, tuple[str, int]]:
        """``{job_id: (state, round)}`` for the jobs that have rounds, in one statement; the
        rule is the domain's ``status_summary`` (a failed round wins)."""
        if not job_ids:
            return {}
        result = await self._session.execute(
            select(
                InterviewRoundRow.job_id, InterviewRoundRow.number, InterviewRoundRow.state
            ).where(InterviewRoundRow.job_id.in_(job_ids))
        )
        grouped: dict[UUID, list[RoundSummary]] = {}
        for job_id, number, state in result.all():
            grouped.setdefault(job_id, []).append(RoundSummary(number, state))
        summary: dict[UUID, tuple[str, int]] = {}
        for grouped_job, rounds in grouped.items():
            latest_state, latest_number = status_summary("", rounds)
            if latest_number is not None:
                summary[grouped_job] = (latest_state, latest_number)
        return summary

    async def rounds_matching(
        self, *, kind: str | None = None, state: str | None = None, source: str | None = None
    ) -> list[InterviewRoundRow]:
        """Rounds by field, for the analytics later (SC-005): no free text is read."""
        stmt = select(InterviewRoundRow).order_by(
            InterviewRoundRow.job_id, InterviewRoundRow.number
        )
        if kind is not None:
            stmt = stmt.where(InterviewRoundRow.kind == kind)
        if state is not None:
            stmt = stmt.where(InterviewRoundRow.state == state)
        if source is not None:
            stmt = stmt.join(
                PipelineDetailsRow, PipelineDetailsRow.job_id == InterviewRoundRow.job_id
            ).where(PipelineDetailsRow.source == source)
        return list((await self._session.execute(stmt)).scalars())
