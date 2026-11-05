"""Repository for workflow runs. Every status change goes through the state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.domain.run_state import (
    PauseReason,
    RunState,
    RunStatus,
    WaitingFor,
    transition,
)
from hiretitan.platform.runtime.infra.models import WorkflowRunRow


class RunNotFoundError(LookupError):
    def __init__(self, run_id: UUID) -> None:
        super().__init__(f"Workflow run {run_id} not found")
        self.run_id = run_id


@dataclass(frozen=True, slots=True)
class Run:
    id: UUID
    workflow: str
    subject_id: UUID | None
    state: RunState
    current_step: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


def _to_run(row: WorkflowRunRow) -> Run:
    return Run(
        id=row.id,
        workflow=row.workflow,
        subject_id=row.subject_id,
        state=RunState(
            RunStatus(row.status),
            pause_reason=PauseReason(row.pause_reason) if row.pause_reason else None,
            waiting_for=WaitingFor(row.waiting_for) if row.waiting_for else None,
        ),
        current_step=row.current_step,
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class RunsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _flush_and_load(self, row: WorkflowRunRow) -> Run:
        await self._session.flush()
        await self._session.refresh(row)
        return _to_run(row)

    async def _locked(self, run_id: UUID) -> WorkflowRunRow:
        row = await self._session.scalar(
            select(WorkflowRunRow).where(WorkflowRunRow.id == run_id).with_for_update()
        )
        if row is None:
            raise RunNotFoundError(run_id)
        return row

    async def create(self, workflow: str, subject_id: UUID | None = None) -> Run:
        row = WorkflowRunRow(workflow=workflow, subject_id=subject_id, status=RunStatus.queued)
        self._session.add(row)
        return await self._flush_and_load(row)

    async def get(self, run_id: UUID) -> Run | None:
        row = await self._session.get(WorkflowRunRow, run_id)
        return _to_run(row) if row else None

    async def transition(
        self,
        run_id: UUID,
        target: RunStatus,
        *,
        pause_reason: PauseReason | None = None,
        waiting_for: WaitingFor | None = None,
        current_step: str | None = None,
        error: str | None = None,
    ) -> Run:
        """Move a run to ``target``; raises ``IllegalTransitionError`` if not allowed.

        ``error`` is kept only when the run fails; any other move clears it.
        """
        row = await self._locked(run_id)
        new = transition(
            _to_run(row).state, target, pause_reason=pause_reason, waiting_for=waiting_for
        )
        row.status = new.status
        row.pause_reason = new.pause_reason
        row.waiting_for = new.waiting_for
        row.error = error if new.status is RunStatus.failed else None
        if current_step is not None:
            row.current_step = current_step
        return await self._flush_and_load(row)

    async def set_step(self, run_id: UUID, step: str) -> Run:
        row = await self._locked(run_id)
        row.current_step = step
        return await self._flush_and_load(row)

    async def list_by_status(self, *statuses: RunStatus) -> list[Run]:
        rows = await self._session.scalars(
            select(WorkflowRunRow)
            .where(WorkflowRunRow.status.in_([s.value for s in statuses]))
            .order_by(WorkflowRunRow.id)  # uuid7: creation order
        )
        return [_to_run(r) for r in rows]
