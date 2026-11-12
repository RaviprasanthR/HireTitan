"""T010: the search tables reject what the data model forbids (data-model.md).

Each test inserts one bad row with plain SQL and expects the database itself to say no, so the
rules hold even if a repository forgets one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

COMPANY = (
    "INSERT INTO app.companies (id, origin, name, resolution{cols}) "
    "VALUES (:id, 'user', 'Acme', 'unresolved'{vals})"
)
JOB = (
    "INSERT INTO app.jobs (id, company_name, title, description, state, first_seen_at, "
    "last_seen_at{cols}) VALUES (:id, 'Acme', 'Backend Engineer', 'text', :state, now(), now()"
    "{vals})"
)
RULESET = (
    "INSERT INTO app.search_rule_sets (id, version, status, rules, based_on) "
    "VALUES (:id, :version, :status, '{}', '{}')"
)
SOURCE = (
    "INSERT INTO app.job_sources (id, job_id, kind, url, seen_at) "
    "VALUES (:id, :job, :kind, :url, now())"
)
DECISION = (
    "INSERT INTO app.relevance_decisions (id, job_id, outcome, decided_by, reason, is_current) "
    "VALUES (:id, :job, :outcome, :by, :reason, :cur)"
)
DUP = (
    "INSERT INTO app.possible_duplicates (id, job_a_id, job_b_id, similarity, status) "
    "VALUES (:id, :a, :b, 95, :s)"
)
_counter = 0


def uid() -> str:
    global _counter
    _counter += 1
    return f"00000000-0000-7000-8000-{_counter:012d}"


async def run(session: AsyncSession, sql: str, **params: Any) -> None:
    await session.execute(text(sql), params)
    await session.flush()


async def rejected(session: AsyncSession, sql: str, **params: Any) -> None:
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await run(session, sql, **params)


def company_sql(extra: str = "", vals: str = "") -> str:
    return COMPANY.format(cols=f", {extra}" if extra else "", vals=f", {vals}" if vals else "")


def job_sql(extra: str = "", vals: str = "") -> str:
    return JOB.format(cols=f", {extra}" if extra else "", vals=f", {vals}" if vals else "")


async def company(session: AsyncSession, extra: str = "", vals: str = "", **p: Any) -> str:
    company_id = uid()
    await run(session, company_sql(extra, vals), id=company_id, **p)
    return company_id


async def bad_company(session: AsyncSession, extra: str, vals: str, **p: Any) -> None:
    await rejected(session, company_sql(extra, vals), id=uid(), **p)


async def job(
    session: AsyncSession, extra: str = "", vals: str = "", state: str = "explore", **p: Any
) -> str:
    job_id = uid()
    await run(session, job_sql(extra, vals), id=job_id, state=state, **p)
    return job_id


async def bad_job(
    session: AsyncSession, extra: str = "", vals: str = "", state: str = "explore", **p: Any
) -> None:
    await rejected(session, job_sql(extra, vals), id=uid(), state=state, **p)


# --- companies -------------------------------------------------------------------------------


async def test_db_rejects_ats_vendor_without_board_id(db_session: AsyncSession) -> None:
    await bad_company(db_session, "ats_vendor", "'greenhouse'")


async def test_db_allows_ats_vendor_with_board_id(db_session: AsyncSession) -> None:
    await company(db_session, "ats_vendor, board_id", "'greenhouse', 'acme'")


async def test_db_rejects_unknown_company_origin_and_resolution(db_session: AsyncSession) -> None:
    sql = "INSERT INTO app.companies (id, origin, name, resolution) VALUES (:id, :o, 'A', :r)"
    await rejected(db_session, sql, id=uid(), o="robot", r="verified")
    await rejected(db_session, sql, id=uid(), o="user", r="guess")


async def test_db_rejects_empty_and_long_company_name(db_session: AsyncSession) -> None:
    sql = (
        "INSERT INTO app.companies (id, origin, name, resolution) "
        "VALUES (:id, 'user', :name, 'unresolved')"
    )
    for name in ("", "x" * 121):
        await rejected(db_session, sql, id=uid(), name=name)


async def test_db_rejects_long_city_and_urls(db_session: AsyncSession) -> None:
    await bad_company(db_session, "city", ":v", v="c" * 81)
    await bad_company(db_session, "website", ":v", v="h" * 501)
    await bad_company(db_session, "careers_url", ":v", v="h" * 501)


async def test_db_rejects_unknown_check_result_and_long_error(db_session: AsyncSession) -> None:
    await bad_company(db_session, "last_check_result", "'maybe'")
    await bad_company(db_session, "last_check_error", ":v", v="e" * 301)


async def test_db_company_key_unique_when_present(db_session: AsyncSession) -> None:
    await company(db_session, "key", "'acme'")
    await bad_company(db_session, "key", "'acme'")
    await company(db_session)  # several rows without a key are fine
    await company(db_session)


# --- rule sets -------------------------------------------------------------------------------


async def test_db_allows_one_approved_rule_set(db_session: AsyncSession) -> None:
    await run(db_session, RULESET, id=uid(), version=1, status="approved")
    await run(db_session, RULESET, id=uid(), version=2, status="superseded")
    await run(db_session, RULESET, id=uid(), version=3, status="proposed")
    await rejected(db_session, RULESET, id=uid(), version=4, status="approved")


async def test_db_rejects_duplicate_rule_set_version_and_bad_status(
    db_session: AsyncSession,
) -> None:
    await run(db_session, RULESET, id=uid(), version=1, status="proposed")
    await rejected(db_session, RULESET, id=uid(), version=1, status="proposed")
    await rejected(db_session, RULESET, id=uid(), version=2, status="draft")


# --- search runs -----------------------------------------------------------------------------


async def make_search_run(
    session: AsyncSession,
    *,
    workflow_status: str = "running",
    mode: str = "rules_and_ai",
    outcome: str | None = None,
    stop_message: str | None = None,
) -> str:
    workflow_id, rule_set_id, run_id = uid(), uid(), uid()
    await run(
        session,
        "INSERT INTO app.workflow_runs (id, workflow, status, pause_reason) "
        "VALUES (:id, 'job_search', :s, CASE WHEN :s = 'paused' THEN 'out_of_credit' END)",
        id=workflow_id,
        s=workflow_status,
    )
    await run(
        session, RULESET, id=rule_set_id, version=int(rule_set_id[-6:]) + 1000, status="superseded"
    )
    await run(
        session,
        "INSERT INTO app.search_runs (id, workflow_run_id, rule_set_id, mode, outcome, "
        "stop_message, company_order) VALUES (:id, :wf, :rs, :mode, :outcome, "
        ":msg, '{}')",
        id=run_id,
        wf=workflow_id,
        rs=rule_set_id,
        mode=mode,
        outcome=outcome,
        msg=stop_message,
    )
    return run_id


async def test_db_accepts_a_search_run(db_session: AsyncSession) -> None:
    await make_search_run(db_session, outcome="out_of_credit", stop_message="No credit.")


@pytest.mark.parametrize(
    "kwargs",
    [{"mode": "everything"}, {"outcome": "gave_up"}, {"stop_message": "m" * 301}],
)
async def test_db_rejects_bad_search_run_values(
    db_session: AsyncSession, kwargs: dict[str, str]
) -> None:
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await make_search_run(db_session, **kwargs)


async def test_db_rejects_second_active_search(db_session: AsyncSession) -> None:
    await make_search_run(db_session, workflow_status="paused")
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await make_search_run(db_session, workflow_status="queued")


async def test_db_allows_a_new_search_after_the_last_finished(db_session: AsyncSession) -> None:
    await make_search_run(db_session, workflow_status="done")
    await make_search_run(db_session, workflow_status="running")


async def test_db_search_run_company_rules(db_session: AsyncSession) -> None:
    search_run = await make_search_run(db_session)
    first, second = await company(db_session), await company(db_session)
    insert = (
        "INSERT INTO app.search_run_companies (search_run_id, company_id, batch_no, result, error)"
        " VALUES (:sr, :c, 1, :res, :err)"
    )
    await run(db_session, insert, sr=search_run, c=first, res="ok", err=None)
    await rejected(db_session, insert, sr=search_run, c=first, res="ok", err=None)
    await rejected(db_session, insert, sr=search_run, c=second, res="weird", err=None)
    await rejected(db_session, insert, sr=search_run, c=second, res="failed", err="e" * 301)


# --- jobs ------------------------------------------------------------------------------------


async def test_db_rejects_applied_without_date_and_date_without_applied(
    db_session: AsyncSession,
) -> None:
    await bad_job(db_session, state="applied")
    await bad_job(db_session, "applied_on", "current_date", state="explore")
    await job(db_session, "applied_on", "current_date", state="applied")


async def test_inquired_on_iff_inquired(db_session: AsyncSession) -> None:
    await bad_job(db_session, state="inquired")
    await bad_job(db_session, "inquired_on", "current_date", state="explore")
    await bad_job(db_session, "inquired_on", "current_date", state="applied")
    await job(db_session, "inquired_on", "current_date", state="inquired")


async def test_db_rejects_bad_job_values(db_session: AsyncSession) -> None:
    await bad_job(db_session, state="maybe")
    await bad_job(db_session, "work_mode", "'office'")
    await bad_job(db_session, "location_text", ":v", v="l" * 201)


async def test_db_rejects_overlong_title_company_and_description(db_session: AsyncSession) -> None:
    for value, limit in (
        ("'Backend Engineer'", 200),  # title
        ("'Acme'", 120),  # company_name
        ("'text'", 30_000),  # description
    ):
        sql = job_sql().replace(value, ":v")
        await rejected(db_session, sql, id=uid(), state="explore", v="x" * (limit + 1))
        await run(db_session, sql, id=uid(), state="explore", v="x" * limit)
    await rejected(
        db_session, job_sql().replace("'Backend Engineer'", "''"), id=uid(), state="explore"
    )


async def test_db_job_sort_key_is_posted_at_else_first_seen(db_session: AsyncSession) -> None:
    posted = await job(db_session, "posted_at", "'2026-01-02T03:04:05+00:00'")
    unposted = await job(db_session)
    rows = (
        await db_session.execute(
            text(
                "SELECT id, sort_key = posted_at AS is_posted, sort_key = first_seen_at AS is_seen "
                "FROM app.jobs WHERE id IN (:a, :b)"
            ),
            {"a": posted, "b": unposted},
        )
    ).all()
    by_id = {str(r.id): r for r in rows}
    assert by_id[posted].is_posted
    assert by_id[unposted].is_seen


async def test_db_job_canonical_url_unique_when_present(db_session: AsyncSession) -> None:
    await job(db_session, "canonical_url", "'https://x.example/1'")
    await bad_job(db_session, "canonical_url", "'https://x.example/1'")
    await job(db_session)  # without a URL, any number
    await job(db_session)


async def test_db_job_vendor_requisition_pair_unique(db_session: AsyncSession) -> None:
    await job(db_session, "ats_vendor, requisition_id", "'lever', 'r1'")
    await bad_job(db_session, "ats_vendor, requisition_id", "'lever', 'r1'")
    await job(db_session, "ats_vendor, requisition_id", "'lever', 'r2'")
    await job(db_session, "ats_vendor", "'lever'")  # the pair only counts when both are set
    await job(db_session, "ats_vendor", "'lever'")


async def test_db_job_survives_its_company_being_removed(db_session: AsyncSession) -> None:
    company_id = await company(db_session)
    job_id = await job(db_session, "company_id", ":cid", cid=company_id)
    await run(db_session, "DELETE FROM app.companies WHERE id = :id", id=company_id)
    row = (
        await db_session.execute(
            text("SELECT company_id FROM app.jobs WHERE id = :i"), {"i": job_id}
        )
    ).one()
    assert row.company_id is None


# --- sources, decisions, duplicates ----------------------------------------------------------


async def test_db_job_source_rules(db_session: AsyncSession) -> None:
    j = await job(db_session)
    url = "https://a.example/1"
    await run(db_session, SOURCE, id=uid(), job=j, kind="company_board", url=url)
    await rejected(db_session, SOURCE, id=uid(), job=j, kind="company_board", url=url)
    await rejected(db_session, SOURCE, id=uid(), job=j, kind="rss", url="https://a.example/2")
    await rejected(db_session, SOURCE, id=uid(), job=j, kind="paste", url="u" * 1001)
    await run(db_session, SOURCE, id=uid(), job=j, kind="paste", url=url)  # another kind is fine


async def test_db_one_current_decision_per_job(db_session: AsyncSession) -> None:
    j = await job(db_session)
    base = {"job": j, "reason": "r"}
    await run(db_session, DECISION, id=uid(), outcome="shown", by="ai", cur=False, **base)
    await run(db_session, DECISION, id=uid(), outcome="skipped", by="rule", cur=True, **base)
    await rejected(db_session, DECISION, id=uid(), outcome="shown", by="person", cur=True, **base)
    other = await job(db_session)
    await run(
        db_session, DECISION, id=uid(), job=other, outcome="shown", by="ai", reason="ok", cur=True
    )


async def test_db_decision_values_and_reason_length(db_session: AsyncSession) -> None:
    j = await job(db_session)
    ok = {"job": j, "outcome": "shown", "by": "ai", "reason": "r", "cur": False}
    for change in ({"outcome": "maybe"}, {"by": "oracle"}, {"reason": ""}, {"reason": "r" * 201}):
        await rejected(db_session, DECISION, id=uid(), **{**ok, **change})
    await run(
        db_session, DECISION, id=uid(), **{**ok, "by": "rules_only_fallback", "reason": "r" * 200}
    )


async def test_db_possible_duplicate_rules(db_session: AsyncSession) -> None:
    a, b, c = sorted([await job(db_session), await job(db_session), await job(db_session)])
    await run(db_session, DUP, id=uid(), a=a, b=b, s="open")
    await rejected(db_session, DUP, id=uid(), a=a, b=b, s="open")  # same pair
    await rejected(db_session, DUP, id=uid(), a=b, b=a, s="open")  # not in id order
    await rejected(db_session, DUP, id=uid(), a=a, b=a, s="open")
    await rejected(db_session, DUP, id=uid(), a=a, b=c, s="pending")


# --- migration -------------------------------------------------------------------------------

TABLES = (
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'app' AND table_type = 'BASE TABLE'"
)
SEARCH_TABLES = {
    "companies",
    "search_rule_sets",
    "search_runs",
    "search_run_companies",
    "jobs",
    "job_sources",
    "relevance_decisions",
    "possible_duplicates",
}


def test_0013_upgrade_and_downgrade(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0013")
    engine = create_engine(fresh_database_url)
    try:
        with engine.connect() as conn:
            assert set(conn.execute(text(TABLES)).scalars()) >= SEARCH_TABLES

        command.downgrade(cfg, "0012")
        with engine.connect() as conn:
            assert not SEARCH_TABLES & set(conn.execute(text(TABLES)).scalars())
            index = conn.execute(
                text(
                    "SELECT 1 FROM pg_indexes WHERE schemaname = 'app' "
                    "AND indexname = 'uq_workflow_runs_one_active_job_search'"
                )
            ).first()
            assert index is None
        command.upgrade(cfg, "head")  # and can be re-applied
    finally:
        engine.dispose()
