"""Contacts and company notes: the tables and their repositories (feature 002b, T005-T007).

Every rule from data-model.md is repeated by the database as a named constraint, so a repository
bug cannot store a value the model forbids. All data here is synthetic (FR-026).
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

CONTACT = (
    "INSERT INTO app.company_contacts (id, company_id, name, name_key, source{cols}) "
    "VALUES (:id, :company, :name, :key, 'typed'{vals})"
)
NOTE = "INSERT INTO app.company_notes (company_id, body, source) VALUES (:company, :body, :source)"
_counter = 0


def uid() -> str:
    global _counter
    _counter += 1
    return f"00000000-0000-7000-9000-{_counter:012d}"


async def run(session: AsyncSession, sql: str, **params: Any) -> None:
    await session.execute(text(sql), params)
    await session.flush()


async def rejected(session: AsyncSession, sql: str, **params: Any) -> None:
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await run(session, sql, **params)


async def company(session: AsyncSession) -> str:
    company_id = uid()
    await run(
        session,
        "INSERT INTO app.companies (id, origin, name, resolution) "
        "VALUES (:id, 'user', 'Example Co', 'unresolved')",
        id=company_id,
    )
    return company_id


def contact_sql(extra: str = "", vals: str = "") -> str:
    return CONTACT.format(cols=f", {extra}" if extra else "", vals=f", {vals}" if vals else "")


async def contact(
    session: AsyncSession,
    company_id: str,
    name: str = "Jane Example",
    key: str = "janeexample",
    extra: str = "",
    vals: str = "",
    **p: Any,
) -> str:
    contact_id = uid()
    await run(
        session,
        contact_sql(extra, vals),
        id=contact_id,
        company=company_id,
        name=name,
        key=key,
        **p,
    )
    return contact_id


async def bad_contact(
    session: AsyncSession,
    company_id: str,
    extra: str = "",
    vals: str = "",
    name: str = "Jane Example",
    key: str = "janeexample",
    **p: Any,
) -> None:
    await rejected(
        session,
        contact_sql(extra, vals),
        id=uid(),
        company=company_id,
        name=name,
        key=key,
        **p,
    )


async def count(session: AsyncSession, table: str) -> int:
    result = await session.execute(text(f"SELECT count(*) FROM app.{table}"))
    return int(result.scalar_one())


# --- T005: tables and constraints -------------------------------------------------------------


async def test_FR006_same_company_and_name_is_unique(db_session: AsyncSession) -> None:
    first = await company(db_session)
    second = await company(db_session)
    await contact(db_session, first)
    await bad_contact(db_session, first)
    await contact(db_session, second)  # the same person name at another company is fine


async def test_FR023_deleting_own_company_removes_contacts_and_note(
    db_session: AsyncSession,
) -> None:
    company_id = await company(db_session)
    await contact(db_session, company_id)
    await run(db_session, NOTE, company=company_id, body="Spoke to HR.", source="typed")

    await run(db_session, "DELETE FROM app.companies WHERE id = :id", id=company_id)

    assert await count(db_session, "company_contacts") == 0
    assert await count(db_session, "company_notes") == 0


async def test_data_model_contact_needs_an_existing_company(db_session: AsyncSession) -> None:
    await bad_contact(db_session, uid())


async def test_data_model_check_constraints(db_session: AsyncSession) -> None:
    c = await company(db_session)
    # confidence values
    await bad_contact(db_session, c, "confidence", "'maybe'")
    await contact(db_session, c, "A", "a", "confidence", "'high'")
    # name and name_key
    await bad_contact(db_session, c, name="", key="x")
    await bad_contact(db_session, c, name="x" * 121, key="y")
    await bad_contact(db_session, c, name="Fine", key="")
    await bad_contact(db_session, c, name="Fine", key="k" * 121)
    # lengths
    await bad_contact(db_session, c, "role", ":v", key="r1", v="r" * 121)
    await bad_contact(db_session, c, "linkedin_url", ":v", key="r2", v="h" * 501)
    await bad_contact(db_session, c, "email", ":v", key="r3", v="e" * 255)
    await bad_contact(db_session, c, "phone", ":v", key="r4", v="1" * 31)
    await bad_contact(db_session, c, "phone", ":v", key="r5", v="1234")
    await bad_contact(db_session, c, "note", ":v", key="r6", v="n" * 2001)
    # source values
    await rejected(
        db_session,
        "INSERT INTO app.company_contacts (id, company_id, name, name_key, source) "
        "VALUES (:id, :c, 'N', 'n', 'robot')",
        id=uid(),
        c=c,
    )
    # company note: body 1-5000, source values, one per company
    await rejected(db_session, NOTE, company=c, body="", source="typed")
    await rejected(db_session, NOTE, company=c, body="n" * 5001, source="typed")
    await rejected(db_session, NOTE, company=c, body="ok", source="robot")
    await run(db_session, NOTE, company=c, body="ok", source="import")
    await rejected(db_session, NOTE, company=c, body="again", source="typed")


async def test_data_model_link_index_is_partial(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'app' "
            "AND indexname = 'ix_company_contacts_company_link'"
        )
    )
    definition = result.scalar_one()
    assert "company_id, link_key" in definition
    assert "WHERE (link_key IS NOT NULL)" in definition


TABLES = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'app'"
NEW_TABLES = {"company_contacts", "company_notes"}


def test_migration_0015_upgrade_and_downgrade(
    fresh_database_url: str, make_alembic_config: Callable[[str], Config]
) -> None:
    cfg = make_alembic_config(fresh_database_url)
    command.upgrade(cfg, "0015")
    engine = create_engine(fresh_database_url)
    try:
        with engine.connect() as conn:
            assert set(conn.execute(text(TABLES)).scalars()) >= NEW_TABLES

        command.downgrade(cfg, "0014")
        with engine.connect() as conn:
            assert not NEW_TABLES & set(conn.execute(text(TABLES)).scalars())
        command.upgrade(cfg, "head")  # and can be re-applied
    finally:
        engine.dispose()
