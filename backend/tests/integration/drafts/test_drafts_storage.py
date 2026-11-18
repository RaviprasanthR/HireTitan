"""Drafts tables, repos, wiring and delete-all (T005, T006, T007): FR-008, FR-009, EC-09."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.drafts_env import DraftsEnv, make_env

from hiretitan.drafts.infra.models import JobKeywordsRow, OutreachDraftRow, TailoredResumeRow
from hiretitan.drafts.infra.repos import DraftsRepo, KeywordsRepo, TailoredRepo
from hiretitan.drafts_wiring import SqlContacts, SqlJobs, SqlProfileFacts, clear_drafts_for_job
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.infra.repos import ContactsRepo, JobsRepo
from hiretitan.setup_wiring import SqlDeleteAllStore

TABLES = {"job_keywords", "outreach_drafts", "tailored_resumes"}


def test_FR008_0021_migration_up_down(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0020")
    engine = create_engine(fresh_database_url)
    try:
        assert not TABLES & set(inspect(engine).get_table_names(schema="app"))
        command.upgrade(cfg, "0021")
        assert set(inspect(engine).get_table_names(schema="app")) >= TABLES
        command.downgrade(cfg, "0020")
        assert not TABLES & set(inspect(engine).get_table_names(schema="app"))
    finally:
        engine.dispose()


def test_DB_0022_indexes_up_down(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0021")
    engine = create_engine(fresh_database_url)
    try:
        command.upgrade(cfg, "0022")
        names = {i["name"] for i in inspect(engine).get_indexes("tailored_resumes", schema="app")}
        assert "ix_tailored_resumes_run_id" in names
        command.downgrade(cfg, "0021")
        names = {i["name"] for i in inspect(engine).get_indexes("tailored_resumes", schema="app")}
        assert "ix_tailored_resumes_run_id" not in names
    finally:
        engine.dispose()


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession]) -> DraftsEnv:
    return await make_env(sessions)


def draft_row(env: DraftsEnv, **over: Any) -> OutreachDraftRow:
    values: dict[str, Any] = {
        "job_id": env.job_id,
        "kind": "connection_request",
        "recipient_name": "Asha",
        "recipient_kind": "other",
        "recipient_key": "typed:asha",
        "status": "writing",
        "cited_fact_ids": [],
    }
    values.update(over)
    return OutreachDraftRow(**values)


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "tweet"},
        {"recipient_kind": "boss"},
        {"status": "done"},
        {"source": "magic"},
        {"recipient_name": ""},
        {"recipient_name": "n" * 121},
        {"recipient_role": "r" * 121},
        {"text": "t" * 2001},
        {"template": "t" * 2001},
    ],
)
async def test_FR008_0021_constraints_reject_bad_values(
    env: DraftsEnv, bad: dict[str, Any]
) -> None:
    async with env.sessions() as session:
        session.add(draft_row(env, **bad))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_FR008_0021_unique_recipient_and_other_checks(env: DraftsEnv) -> None:
    async with env.sessions() as session:
        session.add(draft_row(env))
        await session.flush()
        session.add(draft_row(env))
        with pytest.raises(IntegrityError):
            await session.flush()
    async with env.sessions() as session:
        session.add(
            TailoredResumeRow(job_id=env.job_id, status="writing", document={"x": "y" * 70_000})
        )
        with pytest.raises(IntegrityError):
            await session.flush()
    async with env.sessions() as session:
        session.add(
            JobKeywordsRow(
                job_id=env.job_id,
                description_sha256="short",
                role_summary="r",
                keywords=[],
                must_have=[],
                injection_signals=[],
                prompt_version="1",
                model="m",
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_EC09_0021_cascades_and_set_null(env: DraftsEnv) -> None:
    async with env.sessions() as session:
        draft = draft_row(env, recipient_contact_id=env.contact_id, status="ready", text="hi")
        session.add(draft)
        await session.flush()
        keep = draft.id
        session.add(TailoredResumeRow(job_id=env.job_id, status="writing"))
        await KeywordsRepo(session).save(
            env.job_id,
            sha256="0" * 64,
            role_summary="r",
            keywords=["a"],
            must_have=[],
            injection_signals=[],
            prompt_version="1",
            model="m",
        )
        await session.commit()

    async with env.sessions() as session:  # the contact goes: the link is cleared, the name stays
        await ContactsRepo(session).remove(env.contact_id)
        await session.commit()
    async with env.sessions() as session:
        kept = await session.get(OutreachDraftRow, keep)
        assert kept is not None
        assert kept.recipient_contact_id is None
        assert kept.recipient_name == "Asha"

    async with env.sessions() as session:  # the job row goes: everything about it goes
        await session.execute(text("DELETE FROM app.jobs WHERE id = :id"), {"id": env.job_id})
        await session.commit()
    async with env.sessions() as session:
        for model in (OutreachDraftRow, TailoredResumeRow, JobKeywordsRow):
            assert (await session.scalars(select(model))).all() == []


async def test_FR008_one_current_draft_per_job_kind_recipient(env: DraftsEnv) -> None:
    async with env.sessions() as session:
        repo = DraftsRepo(session)
        args: dict[str, Any] = {
            "kind": "connection_request",
            "recipient_contact_id": None,
            "recipient_name": "Asha",
            "recipient_role": None,
            "recipient_kind": "other",
            "recipient_key": "typed:asha",
        }
        first = await repo.start_writing(env.job_id, **args)
        await repo.save_result(
            first.id,
            template="t",
            text="t",
            source="ai",
            cited_fact_ids=[],
            prompt_name="p",
            prompt_version="1",
            model="m",
        )
        again = await repo.start_writing(env.job_id, **args)

        assert again.id == first.id
        assert again.status == "writing"
        assert len(await repo.list_for_job(env.job_id)) == 1


async def test_FR008_edit_marks_edited_and_keeps_text(env: DraftsEnv) -> None:
    async with env.sessions() as session:
        row = draft_row(env, status="ready", text="before")
        session.add(row)
        await session.flush()
        await DraftsRepo(session).save_edit(row.id, "after")
        assert row.text == "after"
        assert row.edited is True


async def test_US2_AS7_list_for_job_newest_first(env: DraftsEnv) -> None:
    async with env.sessions() as session:
        older = draft_row(env, recipient_key="typed:a", recipient_name="A")
        session.add(older)
        await session.commit()
    async with env.sessions() as session:
        newer = draft_row(env, recipient_key="typed:b", recipient_name="B")
        session.add(newer)
        await session.commit()
    async with env.sessions() as session:
        names = [r.recipient_name for r in await DraftsRepo(session).list_for_job(env.job_id)]
    assert names == ["B", "A"]


async def test_FR009_clear_for_job_removes_all_three(env: DraftsEnv) -> None:
    async with env.sessions() as session:
        session.add(draft_row(env))
        session.add(TailoredResumeRow(job_id=env.job_id, status="writing"))
        await KeywordsRepo(session).save(
            env.job_id,
            sha256="0" * 64,
            role_summary="r",
            keywords=[],
            must_have=[],
            injection_signals=[],
            prompt_version="1",
            model="m",
        )
        await session.commit()
    async with env.sessions() as session:
        await clear_drafts_for_job(session, env.job_id)
        await session.commit()
    async with env.sessions() as session:
        assert await DraftsRepo(session).list_for_job(env.job_id) == []
        assert await TailoredRepo(session).get_for_job(env.job_id) is None
        assert await KeywordsRepo(session).get(env.job_id) is None


async def test_FR005_ports_read_profile_job_and_contacts(
    env: DraftsEnv, sessions: async_sessionmaker[AsyncSession]
) -> None:
    profile = await SqlProfileFacts(sessions).current()
    assert profile is not None
    assert profile.version_id is not None
    assert profile.view.contact.name == "Sam Rivera"
    assert [e.employer for e in profile.view.experience] == ["Northwind Labs", "Initech Works"]
    assert profile.view.experience[0].start == (2021, 3)

    job = await SqlJobs(sessions).get(env.job_id)
    assert job is not None
    assert job.company_name == "Acme"
    assert job.company_id == env.company_id

    contacts = SqlContacts(sessions)
    people = await contacts.for_company(env.company_id)
    assert [(p.id, p.name, p.role) for p in people] == [
        (env.contact_id, "Quillon Fairweather", "Talent Partner")
    ]
    assert (await contacts.get(env.contact_id)) is not None

    async with sessions() as session:
        await JobsRepo(session).set_state(env.job_id, "deleted")
        await session.commit()
    assert await SqlJobs(sessions).get(env.job_id) is None  # a deleted job is not offered


async def test_FR009_delete_all_empties_drafts_tables(env: DraftsEnv) -> None:
    async with env.sessions() as session:
        draft = draft_row(env)
        session.add(draft)
        await RunsRepo(session).create("outreach_draft", subject_id=None)
        await session.commit()
    async with env.sessions() as session:
        await SqlDeleteAllStore(session).wipe_and_reseed()
        await session.commit()
    async with env.sessions() as session:
        for model in (OutreachDraftRow, TailoredResumeRow, JobKeywordsRow):
            assert (await session.scalars(select(model))).all() == []
