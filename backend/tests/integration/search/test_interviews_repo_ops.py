"""The interview repository: contact, source, rounds, questions, summaries (feature 002e, T004)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.integration.search.test_interviews_repo import a_job

from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.repos import InterviewsRepo


async def repo_and_job(session: AsyncSession) -> tuple[InterviewsRepo, UUID]:
    return InterviewsRepo(session), UUID(await a_job(session))


async def test_contact_and_source_round_trip(db_session: AsyncSession) -> None:
    repo, job_id = await repo_and_job(db_session)
    assert (await repo.details(job_id)).details is None

    await repo.upsert_contact(job_id, ContactFields(name="Asha Rao", role="Recruiter"))
    await repo.set_source(job_id, "hiring_firm", "TalentBridge")
    row = (await repo.details(job_id)).details

    assert row is not None
    assert (row.contact_name, row.contact_role, row.contact_email) == (
        "Asha Rao",
        "Recruiter",
        None,
    )
    assert (row.source, row.firm_name) == ("hiring_firm", "TalentBridge")

    await repo.upsert_contact(job_id, ContactFields(name="Ben"))  # replaces every contact field
    await repo.set_source(job_id, "direct", None)
    row = (await repo.details(job_id)).details
    assert row is not None
    assert (row.contact_name, row.contact_role) == ("Ben", None)
    assert (row.source, row.firm_name) == ("direct", None)


async def test_clearing_everything_removes_the_row(db_session: AsyncSession) -> None:
    repo, job_id = await repo_and_job(db_session)
    await repo.upsert_contact(job_id, ContactFields(name="Asha"))
    await repo.set_source(job_id, "direct", None)

    await repo.clear_contact(job_id)
    row = (await repo.details(job_id)).details
    assert row is not None
    assert row.contact_name is None
    assert row.source == "direct"

    await repo.set_source(job_id, None, None)
    assert (await repo.details(job_id)).details is None


async def test_US2_AS6_delete_keeps_other_numbers(db_session: AsyncSession) -> None:
    repo, job_id = await repo_and_job(db_session)
    first = await repo.add_round(job_id, kind="screening")
    second = await repo.add_round(job_id, kind="technical")
    third = await repo.add_round(job_id, kind="hr")
    assert [r.number for r in (first, second, third)] == [1, 2, 3]

    await repo.delete_round(second.id)
    assert [r.round.number for r in (await repo.details(job_id)).rounds] == [1, 3]

    await repo.delete_round(third.id)  # the top one: its number is used again
    again = await repo.add_round(job_id, kind="hr")
    assert again.number == 2


async def test_round_defaults_and_update(db_session: AsyncSession) -> None:
    repo, job_id = await repo_and_job(db_session)
    when = datetime(2026, 11, 14, 10, 30, tzinfo=UTC)
    created = await repo.add_round(
        job_id, kind="technical", scheduled_at=when, interviewers="Ben (EM)"
    )
    assert (created.state, created.scheduled_at, created.interviewers) == (
        "scheduled",
        when,
        "Ben (EM)",
    )

    updated = await repo.update_round(
        created.id, {"state": "cleared", "feedback": "Good.\n\nSolid."}
    )
    assert (updated.state, updated.feedback) == ("cleared", "Good.\n\nSolid.")
    cleared = await repo.update_round(created.id, {"scheduled_at": None, "feedback": None})
    assert (cleared.scheduled_at, cleared.feedback, cleared.state) == (None, None, "cleared")


async def test_US3_AS1_questions_in_order(db_session: AsyncSession) -> None:
    repo, job_id = await repo_and_job(db_session)
    round_row = await repo.add_round(job_id, kind="technical")
    first = await repo.add_question(round_row.id, "Design a rate limiter", "Token bucket")
    await repo.add_question(round_row.id, "Why us?", None)
    third = await repo.add_question(round_row.id, "Any questions?", None)

    await repo.delete_question(first.id)
    extra = await repo.add_question(round_row.id, "Last one", "Yes")
    await repo.update_question(third.id, {"answer": "Team size?"})

    questions = (await repo.details(job_id)).rounds[0].questions
    assert [(q.question, q.answer) for q in questions] == [
        ("Why us?", None),
        ("Any questions?", "Team size?"),
        ("Last one", "Yes"),
    ]
    assert extra.position == 4  # new = max + 1; the gap left by the delete stays


async def test_delete_round_removes_its_questions(db_session: AsyncSession) -> None:
    repo, job_id = await repo_and_job(db_session)
    round_row = await repo.add_round(job_id, kind="hr")
    await repo.add_question(round_row.id, "Why?", None)

    await repo.delete_round(round_row.id)

    count = (
        await db_session.execute(text("SELECT count(*) FROM app.interview_questions"))
    ).scalar()
    assert count == 0


async def test_delete_for_job_removes_everything_of_that_job_only(
    db_session: AsyncSession,
) -> None:
    repo, job_id = await repo_and_job(db_session)
    other = UUID(await a_job(db_session))
    for target in (job_id, other):
        await repo.upsert_contact(target, ContactFields(name="Asha"))
        row = await repo.add_round(target, kind="hr")
        await repo.add_question(row.id, "Why?", None)

    await repo.delete_for_job(job_id)

    gone = await repo.details(job_id)
    kept = await repo.details(other)
    assert gone.details is None
    assert gone.rounds == []
    assert kept.details is not None
    assert len(kept.rounds) == 1
    assert len(kept.rounds[0].questions) == 1


async def test_summaries_in_one_query(db_session: AsyncSession) -> None:
    repo, one = await repo_and_job(db_session)
    two = UUID(await a_job(db_session))
    three = UUID(await a_job(db_session))
    none = UUID(await a_job(db_session))
    await repo.add_round(one, kind="screening")
    second = await repo.add_round(one, kind="technical")
    await repo.update_round(second.id, {"state": "failed"})
    await repo.add_round(one, kind="hr")  # a later round does not hide the failure (FR-007)
    cleared = await repo.add_round(two, kind="hr")
    await repo.update_round(cleared.id, {"state": "cleared"})
    await repo.add_round(three, kind="hr")
    await repo.add_round(three, kind="managerial")

    statements: list[str] = []

    def record(*args: object) -> None:
        statements.append(str(args[2]))

    sync_engine = db_session.get_bind()
    event.listen(sync_engine, "before_cursor_execute", record)
    try:
        summaries = await repo.summaries([one, two, three, none])
    finally:
        event.remove(sync_engine, "before_cursor_execute", record)

    assert summaries == {one: ("failed", 2), two: ("cleared", 1), three: ("scheduled", 2)}
    assert len(statements) == 1


async def test_SC005_rounds_matching_by_field(db_session: AsyncSession) -> None:
    repo, firm_job = await repo_and_job(db_session)
    direct_job = UUID(await a_job(db_session))
    await repo.set_source(firm_job, "hiring_firm", "TalentBridge")
    await repo.set_source(direct_job, "direct", None)
    a = await repo.add_round(firm_job, kind="technical")
    await repo.update_round(a.id, {"state": "failed"})
    b = await repo.add_round(direct_job, kind="technical")
    await repo.update_round(b.id, {"state": "cleared"})
    await repo.add_round(direct_job, kind="hr")

    assert [r.id for r in await repo.rounds_matching(kind="technical", state="failed")] == [a.id]
    assert len(await repo.rounds_matching(kind="technical")) == 2
    assert [r.id for r in await repo.rounds_matching(source="hiring_firm")] == [a.id]
    assert len(await repo.rounds_matching(source="direct")) == 2
    assert len(await repo.rounds_matching()) == 3


async def test_review_concurrent_rounds_get_distinct_numbers(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        job_id = UUID(await a_job(session))
        await session.commit()

    async def add() -> int:
        async with sessions() as session:
            row = await InterviewsRepo(session).add_round(job_id, kind="technical")
            await session.commit()
            return row.number

    numbers = await asyncio.gather(*(add() for _ in range(4)))

    assert sorted(numbers) == [1, 2, 3, 4]


async def test_review_concurrent_questions_get_distinct_positions(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        job_id = UUID(await a_job(session))
        round_id = (await InterviewsRepo(session).add_round(job_id, kind="hr")).id
        await session.commit()

    async def add(n: int) -> int:
        async with sessions() as session:
            row = await InterviewsRepo(session).add_question(round_id, f"Q{n}", None)
            await session.commit()
            return row.position

    positions = await asyncio.gather(*(add(n) for n in range(4)))

    assert sorted(positions) == [1, 2, 3, 4]


async def test_review_a_question_position_is_unique_per_round(db_session: AsyncSession) -> None:
    repo, job_id = await repo_and_job(db_session)
    round_row = await repo.add_round(job_id, kind="hr")
    await repo.add_question(round_row.id, "Why?", None)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO app.interview_questions (id, round_id, position, question)"
                    " VALUES (gen_random_uuid(), :r, 1, 'Again')"
                ),
                {"r": round_row.id},
            )
