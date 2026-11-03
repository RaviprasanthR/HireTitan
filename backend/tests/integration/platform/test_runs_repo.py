"""T013: ``app.workflow_runs`` and its repository (FR-013: run status is persisted)."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.db import uuid7
from hiretitan.platform.runtime.domain.run_state import (
    IllegalTransitionError,
    PauseReason,
    RunStatus,
    WaitingFor,
)
from hiretitan.platform.runtime.infra.runs_repo import RunNotFoundError, RunsRepo


@pytest.fixture
def repo(db_session: AsyncSession) -> RunsRepo:
    return RunsRepo(db_session)


async def _stored_status(session: AsyncSession, run_id: UUID) -> tuple[str, str | None, str | None]:
    row = (
        await session.execute(
            text("SELECT status, pause_reason, waiting_for FROM app.workflow_runs WHERE id = :id"),
            {"id": run_id},
        )
    ).one()
    return row.status, row.pause_reason, row.waiting_for


async def test_FR013_run_status_persisted(repo: RunsRepo, db_session: AsyncSession) -> None:
    subject = uuid7()
    run = await repo.create("profile_ingest", subject_id=subject)
    assert run.state.status is RunStatus.queued
    assert run.id.version == 7

    await repo.transition(run.id, RunStatus.running, current_step="parse")
    await repo.transition(run.id, RunStatus.paused, pause_reason=PauseReason.key_missing)

    assert await _stored_status(db_session, run.id) == ("paused", "key_missing", None)
    loaded = await repo.get(run.id)
    assert loaded is not None
    assert loaded.workflow == "profile_ingest"
    assert loaded.subject_id == subject
    assert loaded.state.pause_reason is PauseReason.key_missing
    assert loaded.current_step == "parse"


async def test_transition_uses_state_machine(repo: RunsRepo, db_session: AsyncSession) -> None:
    run = await repo.create("profile_ingest")
    with pytest.raises(IllegalTransitionError):
        await repo.transition(run.id, RunStatus.done)
    assert await _stored_status(db_session, run.id) == ("queued", None, None)


async def test_transition_clears_reasons_and_records_error(repo: RunsRepo) -> None:
    run = await repo.create("profile_ingest")
    await repo.transition(run.id, RunStatus.running)
    await repo.transition(run.id, RunStatus.awaiting_review, waiting_for=WaitingFor.profile_review)
    requeued = await repo.transition(run.id, RunStatus.queued)
    assert requeued.state.waiting_for is None

    await repo.transition(run.id, RunStatus.running)
    failed = await repo.transition(run.id, RunStatus.failed, error="Could not read the file")
    assert failed.error == "Could not read the file"
    retried = await repo.transition(run.id, RunStatus.queued)
    assert retried.error is None


async def test_db_rejects_paused_without_reason(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="pause_reason"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO app.workflow_runs (id, workflow, status) "
                    "VALUES (:id, 'profile_ingest', 'paused')"
                ),
                {"id": uuid7()},
            )


@pytest.mark.parametrize(
    ("status", "pause_reason", "waiting_for", "constraint"),
    [
        ("awaiting_review", None, None, "waiting_for"),
        ("running", "key_missing", None, "pause_reason"),
        ("done", None, "profile_review", "waiting_for"),
        ("sleeping", None, None, "status"),
        ("paused", "tired", None, "pause_reason"),
    ],
)
async def test_db_rejects_inconsistent_rows(
    db_session: AsyncSession,
    status: str,
    pause_reason: str | None,
    waiting_for: str | None,
    constraint: str,
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO app.workflow_runs"
                    " (id, workflow, status, pause_reason, waiting_for)"
                    " VALUES (:id, 'profile_ingest', :status, :pause_reason, :waiting_for)"
                ),
                {
                    "id": uuid7(),
                    "status": status,
                    "pause_reason": pause_reason,
                    "waiting_for": waiting_for,
                },
            )


async def test_list_by_status(repo: RunsRepo) -> None:
    a = await repo.create("profile_ingest")
    b = await repo.create("profile_ingest")
    await repo.transition(b.id, RunStatus.running)
    await repo.transition(b.id, RunStatus.paused, pause_reason=PauseReason.budget_reached)

    paused = await repo.list_by_status(RunStatus.paused)
    assert [r.id for r in paused] == [b.id]
    both = await repo.list_by_status(RunStatus.queued, RunStatus.paused)
    assert [r.id for r in both] == [a.id, b.id]  # oldest first


async def test_set_step_keeps_status(repo: RunsRepo) -> None:
    run = await repo.create("profile_ingest")
    await repo.transition(run.id, RunStatus.running)
    updated = await repo.set_step(run.id, "extract")
    assert updated.current_step == "extract"
    assert updated.state.status is RunStatus.running


async def test_unknown_run(repo: RunsRepo) -> None:
    assert await repo.get(uuid7()) is None
    with pytest.raises(RunNotFoundError):
        await repo.transition(uuid7(), RunStatus.running)
