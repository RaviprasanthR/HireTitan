"""Interview tracking tables: the database itself refuses what the data model forbids (002e).

Plain SQL again, so the rules hold even if a repository forgets one. The repository's own
behaviour (numbering, ordering, summaries) is tested further down.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.search.test_schema import job, rejected, run, uid

DETAILS = "INSERT INTO app.job_pipeline_details (job_id{cols}) VALUES (:job{vals})"
ROUND = (
    "INSERT INTO app.interview_rounds (id, job_id, number, kind, state{cols}) "
    "VALUES (:id, :job, :n, :kind, :state{vals})"
)
QUESTION = (
    "INSERT INTO app.interview_questions (id, round_id, position, question{cols}) "
    "VALUES (:id, :round, :pos, :q{vals})"
)


def details_sql(cols: str = "", vals: str = "") -> str:
    return DETAILS.format(cols=f", {cols}" if cols else "", vals=f", {vals}" if vals else "")


def round_sql(cols: str = "", vals: str = "") -> str:
    return ROUND.format(cols=f", {cols}" if cols else "", vals=f", {vals}" if vals else "")


async def a_job(session: AsyncSession) -> str:
    return await job(session, "applied_on", "current_date", state="applied")


async def a_round(
    session: AsyncSession, job_id: str, number: int = 1, kind: str = "technical", **p: Any
) -> str:
    round_id = uid()
    await run(
        session,
        round_sql(),
        id=round_id,
        job=job_id,
        n=number,
        kind=kind,
        state=p.pop("state", "scheduled"),
    )
    return round_id


async def test_FR003_firm_iff_hiring_firm(db_session: AsyncSession) -> None:
    job_id = await a_job(db_session)

    # a hiring firm needs a name, and only a hiring firm has one
    await rejected(db_session, details_sql("source", "'hiring_firm'"), job=job_id)
    await rejected(
        db_session, details_sql("source, firm_name", "'direct', 'TalentBridge'"), job=job_id
    )
    await rejected(db_session, details_sql("firm_name", "'TalentBridge'"), job=job_id)
    await run(
        db_session, details_sql("source, firm_name", "'hiring_firm', 'TalentBridge'"), job=job_id
    )


async def test_FR003_direct_and_unset_source_have_no_firm(db_session: AsyncSession) -> None:
    await run(db_session, details_sql("source", "'direct'"), job=await a_job(db_session))
    await run(db_session, details_sql(), job=await a_job(db_session))


async def test_FR009_checks_reject_bad_values(db_session: AsyncSession) -> None:
    job_id = await a_job(db_session)

    # source and contact rules
    await rejected(db_session, details_sql("source", "'agency'"), job=job_id)
    await rejected(db_session, details_sql("contact_email", "'a@example.com'"), job=job_id)
    await rejected(db_session, details_sql("contact_name", "''"), job=job_id)
    await rejected(db_session, details_sql("contact_name", ":n"), job=job_id, n="n" * 121)
    await rejected(
        db_session, details_sql("contact_name, contact_phone", "'A', 'call me'"), job=job_id
    )

    # round rules
    await rejected(
        db_session, round_sql(), id=uid(), job=job_id, n=1, kind="coffee", state="scheduled"
    )
    await rejected(db_session, round_sql(), id=uid(), job=job_id, n=1, kind="hr", state="won")
    await rejected(db_session, round_sql(), id=uid(), job=job_id, n=0, kind="hr", state="scheduled")
    await rejected(
        db_session,
        round_sql("interviewers", ":iv"),
        id=uid(),
        job=job_id,
        n=1,
        kind="hr",
        state="scheduled",
        iv="i" * 301,
    )
    await rejected(
        db_session,
        round_sql("feedback", ":f"),
        id=uid(),
        job=job_id,
        n=1,
        kind="hr",
        state="scheduled",
        f="f" * 10_001,
    )

    # question rules
    round_id = await a_round(db_session, job_id)
    await rejected(
        db_session, QUESTION.format(cols="", vals=""), id=uid(), round=round_id, pos=0, q="Why?"
    )
    await rejected(
        db_session, QUESTION.format(cols="", vals=""), id=uid(), round=round_id, pos=1, q=""
    )
    await rejected(
        db_session,
        QUESTION.format(cols="", vals=""),
        id=uid(),
        round=round_id,
        pos=1,
        q="q" * 2_001,
    )
    await rejected(
        db_session,
        QUESTION.format(cols=", answer", vals=", :a"),
        id=uid(),
        round=round_id,
        pos=1,
        q="Why?",
        a="a" * 10_001,
    )
    await run(
        db_session, QUESTION.format(cols="", vals=""), id=uid(), round=round_id, pos=1, q="Why?"
    )


async def test_FR004_unique_round_number(db_session: AsyncSession) -> None:
    job_id = await a_job(db_session)
    await a_round(db_session, job_id, 1)

    await rejected(db_session, round_sql(), id=uid(), job=job_id, n=1, kind="hr", state="scheduled")
    await a_round(db_session, job_id, 2)  # another number is fine
    await a_round(db_session, await a_job(db_session), 1)  # and another job may have round 1


async def test_FR011_rows_go_with_their_job(db_session: AsyncSession) -> None:
    job_id = await a_job(db_session)
    await run(db_session, details_sql("source", "'direct'"), job=job_id)
    round_id = await a_round(db_session, job_id)
    await run(
        db_session, QUESTION.format(cols="", vals=""), id=uid(), round=round_id, pos=1, q="Why?"
    )

    await run(db_session, "DELETE FROM app.jobs WHERE id = :id", id=job_id)

    for table in ("job_pipeline_details", "interview_rounds", "interview_questions"):
        count = (await db_session.execute(text(f"SELECT count(*) FROM app.{table}"))).scalar()
        assert count == 0, table
