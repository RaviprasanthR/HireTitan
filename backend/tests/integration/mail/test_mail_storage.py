"""Mail tables (T006): FR-004, FR-010, FR-011, FR-016, FR-026, data-model.md. Real PostgreSQL."""

from __future__ import annotations

import asyncio
import selectors
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fakes.mail_env import make_job, make_run

from hiretitan.mail.infra.models import (
    MailCheckRow,
    MailConnectionRow,
    MailReadMessageRow,
    MailSenderRow,
)
from hiretitan.platform.db import create_engine as create_engine_for
from hiretitan.platform.db import session_factory
from hiretitan.search.infra.models import AlertSightingRow, JobSourceRow

NOW = datetime(2026, 11, 18, 9, tzinfo=UTC)
TABLES = {
    "mail_connection",
    "mail_senders",
    "mail_read_messages",
    "mail_checks",
    "alert_sightings",
}


def test_DB_0023_migration_up_down(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0022")
    engine = create_engine(fresh_database_url)
    try:
        assert not TABLES & set(inspect(engine).get_table_names(schema="app"))
        command.upgrade(cfg, "0023")
        assert set(inspect(engine).get_table_names(schema="app")) >= TABLES
        command.downgrade(cfg, "0022")
        assert not TABLES & set(inspect(engine).get_table_names(schema="app"))
    finally:
        engine.dispose()


def connection(**over: Any) -> MailConnectionRow:
    values: dict[str, Any] = {
        "provider": "gmail",
        "address": "person@example.invalid",
        "state": "connected",
        "connected_at": NOW,
    }
    values.update(over)
    return MailConnectionRow(**values)


def sender(**over: Any) -> MailSenderRow:
    values: dict[str, Any] = {
        "address": "alerts@jobsite.example.invalid",
        "site": "naukri",
        "purpose": "job_alert",
        "built_in": True,
        "enabled": True,
    }
    values.update(over)
    return MailSenderRow(**values)


def read_message(**over: Any) -> MailReadMessageRow:
    values: dict[str, Any] = {
        "provider_message_id": "18c0ffee00000001",
        "sender": "alerts@jobsite.example.invalid",
        "received_at": NOW,
        "purpose": "job_alert",
        "outcome": "read",
        "reader": "naukri",
        "jobs_found": 3,
        "injection_signals": [],
        "read_at": NOW,
    }
    values.update(over)
    return MailReadMessageRow(**values)


def check(run_id: UUID, **over: Any) -> MailCheckRow:
    values: dict[str, Any] = {
        "search_run_id": run_id,
        "trigger": "button",
        "window_start": NOW,
        "emails_listed": 5,
        "emails_skipped": 1,
        "emails_read": 3,
        "emails_unreadable": 1,
        "more_remaining": False,
        "ended": "finished",
    }
    values.update(over)
    return MailCheckRow(**values)


async def rejected(session: AsyncSession, row: object) -> None:
    session.add(row)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.parametrize(
    "bad",
    [
        {"state": "asleep"},
        {"provider": "outlook"},
        {"address": "ab"},
        {"address": "x" * 321},
        {"last_error": "e" * 301},
    ],
)
async def test_FR004_connection_rejects_bad_values(
    db_session: AsyncSession, bad: dict[str, Any]
) -> None:
    await rejected(db_session, connection(**bad))


async def test_FR004_only_one_connection(db_session: AsyncSession) -> None:
    db_session.add(connection())
    await db_session.flush()
    await rejected(db_session, connection(address="other@example.invalid"))


@pytest.mark.parametrize(
    "bad",
    [
        {"address": "ab"},
        {"address": "x" * 321},
        {"address": "Upper@Case.example.invalid"},
        {"site": "somesite"},
        {"purpose": "chat"},
    ],
)
async def test_FR010_sender_rejects_bad_values(
    db_session: AsyncSession, bad: dict[str, Any]
) -> None:
    await rejected(db_session, sender(**bad))


async def test_FR010_sender_address_is_unique(db_session: AsyncSession) -> None:
    db_session.add(sender())
    await db_session.flush()
    await rejected(db_session, sender(site="indeed"))


@pytest.mark.parametrize(
    "bad",
    [
        {"outcome": "maybe"},
        {"purpose": "chat"},
        {"jobs_found": -1},
        {"jobs_found": 61},
        {"provider_message_id": "x" * 65},
        {"injection_signals": {"not": "an array"}},
        {"sender": "x" * 321},
        {"outcome": "read", "reader": None},  # a read email says which reader read it
        {"outcome": "no_jobs", "jobs_found": 2},  # jobs only come from a read email
        {"outcome": "unreadable", "jobs_found": 1},
    ],
)
async def test_FR011_read_message_rejects_bad_values(
    db_session: AsyncSession, bad: dict[str, Any]
) -> None:
    await rejected(db_session, read_message(**bad))


async def test_FR011_a_message_is_read_once(db_session: AsyncSession) -> None:
    db_session.add(read_message())
    await db_session.flush()
    await rejected(db_session, read_message(sender="someone@else.example.invalid"))


@pytest.mark.parametrize(
    "bad",
    [
        {"trigger": "whenever"},
        {"ended": "exploded"},
        {"emails_listed": -1},
        {"emails_read": 4},  # a finished check's counts must add up (FR-026)
        {"emails_unreadable": -1, "emails_listed": 3},
    ],
)
async def test_FR026_check_rejects_bad_values(
    db_session: AsyncSession, bad: dict[str, Any]
) -> None:
    run_id = await make_run(db_session)
    await rejected(db_session, check(run_id, **bad))


async def test_FR026_a_stopped_check_need_not_add_up(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)
    db_session.add(check(run_id, ended="stopped", emails_listed=9, emails_read=2))

    await db_session.flush()


async def test_FR026_one_check_per_search_run(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)
    db_session.add(check(run_id))
    await db_session.flush()
    await rejected(db_session, check(run_id))


async def test_FR019_email_alert_is_a_source_kind_and_mail_alerts_a_run_mode(
    db_session: AsyncSession,
) -> None:
    run_id = await make_run(db_session, mode="mail_alerts")
    job_id = await make_job(db_session)
    db_session.add(
        JobSourceRow(
            job_id=job_id,
            kind="email_alert",
            url="https://www.example.invalid/job/1",
            search_run_id=run_id,
            seen_at=NOW,
        )
    )

    await db_session.flush()
    await rejected(
        db_session,
        JobSourceRow(job_id=job_id, kind="carrier_pigeon", url="https://x.invalid/", seen_at=NOW),
    )


def sighting(job_id: UUID, message_id: UUID | None, **over: Any) -> AlertSightingRow:
    values: dict[str, Any] = {
        "job_id": job_id,
        "read_message_id": message_id,
        "site": "naukri",
        "link": "https://www.naukri.com/job-listings-x-191100000001",
        "alert_date": NOW,
    }
    values.update(over)
    return AlertSightingRow(**values)


async def test_FR022_sighting_rejects_bad_values_and_a_repeat(db_session: AsyncSession) -> None:
    job_id = await make_job(db_session)
    message = read_message()
    db_session.add(message)
    await db_session.flush()
    db_session.add(sighting(job_id, message.id))
    await db_session.flush()

    await rejected(db_session, sighting(job_id, message.id))  # the same pair twice
    await rejected(db_session, sighting(job_id, None, site="somesite"))
    await rejected(db_session, sighting(job_id, None, link="h" * 2001))


async def test_FR004_cascades_and_set_null(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)
    job_id = await make_job(db_session)
    mail_check = check(run_id)
    db_session.add(mail_check)
    await db_session.flush()
    message = read_message(mail_check_id=mail_check.id)
    db_session.add(message)
    await db_session.flush()
    seen = sighting(job_id, message.id)
    db_session.add(seen)
    await db_session.flush()

    # deleting the read-email records (Disconnect) keeps the sighting and the job
    await db_session.execute(text("DELETE FROM app.mail_read_messages"))
    await db_session.refresh(seen)
    assert seen.read_message_id is None

    # deleting a job removes its sightings
    await db_session.execute(text("DELETE FROM app.jobs WHERE id = :id"), {"id": job_id})
    assert (await db_session.scalars(select(AlertSightingRow))).first() is None

    # deleting a search run removes its mail check
    await db_session.execute(text("DELETE FROM app.search_runs WHERE id = :id"), {"id": run_id})
    assert (await db_session.scalars(select(MailCheckRow))).first() is None


async def test_FR004_deleting_a_check_keeps_the_read_message(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)
    mail_check = check(run_id)
    db_session.add(mail_check)
    await db_session.flush()
    message = read_message(mail_check_id=mail_check.id)
    db_session.add(message)
    await db_session.flush()

    await db_session.execute(text("DELETE FROM app.mail_checks"))
    await db_session.refresh(message)

    assert message.mail_check_id is None


async def test_FR004_disconnect_leaves_many_sightings_of_one_job_with_no_message(
    db_session: AsyncSession,
) -> None:
    # Disconnect sets read_message_id to NULL on every sighting; one job seen in two alerts must
    # not then collide with itself (so the unique must not treat NULLs as equal)
    job_id = await make_job(db_session)
    first, second = read_message(), read_message(provider_message_id="18c0ffee00000002")
    db_session.add_all([first, second])
    await db_session.flush()
    db_session.add_all([sighting(job_id, first.id), sighting(job_id, second.id)])
    await db_session.flush()

    await db_session.execute(text("DELETE FROM app.mail_read_messages"))

    rows = (await db_session.scalars(select(AlertSightingRow))).all()
    assert [r.read_message_id for r in rows] == [None, None]


async def test_DB_0023_names_and_indexes(db_session: AsyncSession) -> None:
    names = set(
        (
            await db_session.scalars(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'app'"
                    " AND tablename IN ('alert_sightings', 'mail_read_messages')"
                )
            )
        ).all()
    )

    assert "uq_alert_sightings_job_id_read_message_id" in names
    assert "ix_alert_sightings_job_id" not in names  # the unique already leads with job_id
    assert "ix_mail_read_messages_mail_check_id" in names


def test_DB_0023_downgrade_converts_instead_of_deleting(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    # seeded at head (the models match the newest schema), then taken back down through 0023
    command.upgrade(cfg, "head")

    async def seed() -> tuple[UUID, UUID]:
        engine = create_engine_for(fresh_database_url)
        try:
            async with session_factory(engine)() as session:
                run_id = await make_run(session)  # mode mail_alerts
                job_id = await make_job(session)
                session.add_all(
                    [
                        JobSourceRow(
                            job_id=job_id,
                            kind="email_alert",
                            url="https://a.invalid/1",
                            seen_at=NOW,
                        ),
                        # the same address already held as a paste: converting must not clash
                        JobSourceRow(
                            job_id=job_id, kind="paste", url="https://a.invalid/1", seen_at=NOW
                        ),
                        JobSourceRow(
                            job_id=job_id,
                            kind="email_alert",
                            url="https://a.invalid/2",
                            seen_at=NOW,
                        ),
                    ]
                )
                await session.commit()
                return run_id, job_id
        finally:
            await engine.dispose()

    run_id, job_id = asyncio.run(
        seed(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    )

    command.downgrade(cfg, "0022")  # must not fail, and must not delete the run or the sources

    engine = create_engine(fresh_database_url)
    try:
        with engine.connect() as conn:
            mode = conn.execute(
                text("SELECT mode FROM app.search_runs WHERE id = :id"), {"id": run_id}
            ).scalar_one()
            sources = conn.execute(
                text("SELECT kind, url FROM app.job_sources WHERE job_id = :id ORDER BY url"),
                {"id": job_id},
            ).all()
    finally:
        engine.dispose()
    assert mode == "rules_only"
    assert [tuple(r) for r in sources] == [
        ("paste", "https://a.invalid/1"),
        ("paste", "https://a.invalid/2"),
    ]


async def test_FR026_a_check_can_end_as_failed(db_session: AsyncSession) -> None:
    run_id = await make_run(db_session)
    db_session.add(check(run_id, ended="failed", emails_listed=9, emails_read=2))

    await db_session.flush()


async def test_FR021_only_one_mail_check_can_be_active(db_session: AsyncSession) -> None:
    from hiretitan.platform.runtime.infra.runs_repo import RunsRepo

    await RunsRepo(db_session).create("mail_check")
    with pytest.raises(IntegrityError):
        await RunsRepo(db_session).create("mail_check")
    await db_session.rollback()


async def test_DB_0024_the_name_look_ups_have_indexes(db_session: AsyncSession) -> None:
    names = set(
        (
            await db_session.scalars(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'app'"
                    " AND tablename IN ('jobs', 'companies')"
                )
            )
        ).all()
    )

    assert {"ix_jobs_company_name_lower", "ix_companies_name_lower"} <= names


def test_DB_0024_up_and_down(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0024")
    engine = create_engine(fresh_database_url)
    try:
        command.downgrade(cfg, "0023")
        with engine.connect() as conn:
            left = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes"
                    " WHERE indexname = 'ix_jobs_company_name_lower'"
                )
            ).all()
        assert left == []
    finally:
        engine.dispose()
