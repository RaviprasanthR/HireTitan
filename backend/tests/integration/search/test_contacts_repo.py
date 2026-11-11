"""Contacts and company notes: the tables and their repositories (feature 002b, T005-T007).

Every rule from data-model.md is repeated by the database as a named constraint, so a repository
bug cannot store a value the model forbids. All data here is synthetic (FR-026).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.search.application.seed import SeedError, load_seed
from hiretitan.search.domain.contacts import ContactFields, link_key, name_key
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, NotesRepo
from hiretitan.setup_wiring import SqlDeleteAllStore

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


# --- T006: repositories -----------------------------------------------------------------------


async def own_company(session: AsyncSession, name: str = "Example Co") -> Any:
    row = await CompaniesRepo(session).add(name=name, origin="user", resolution="unresolved")
    return row.id


def fields(name: str = "Jane Example", **kw: str | None) -> ContactFields:
    return ContactFields(name=name, **kw)


async def test_repo_add_get_list_update_delete_contact(db_session: AsyncSession) -> None:
    repo = ContactsRepo(db_session)
    company_id = await own_company(db_session)

    zed = await repo.add(company_id, fields("Zed Sample"), source="typed")
    jane = await repo.add(
        company_id,
        fields("Jane Example", role="Recruiter", linkedin_url="https://www.linkedin.com/in/jane/"),
        source="import",
    )

    assert jane.name_key == name_key("Jane Example")
    assert jane.link_key == "linkedin.com/in/jane"
    assert jane.source == "import"
    assert (await repo.get(jane.id)) is not None
    assert [c.name for c in await repo.list_for_company(company_id)] == [
        "Jane Example",
        "Zed Sample",
    ]

    updated = await repo.update(
        jane.id, fields("Jane Q Example", role="Talent Lead", confidence="high")
    )
    assert updated.name == "Jane Q Example"
    assert updated.name_key == name_key("Jane Q Example")
    assert updated.link_key is None  # the link was not given, so it is cleared
    assert updated.role == "Talent Lead"
    assert updated.source == "import"  # an edit does not change where the row came from

    await repo.remove(zed.id)
    assert await repo.get(zed.id) is None
    assert [c.name for c in await repo.list_for_company(company_id)] == ["Jane Q Example"]


async def test_repo_find_by_name_key_and_by_link_key(db_session: AsyncSession) -> None:
    repo = ContactsRepo(db_session)
    company_id = await own_company(db_session)
    other_id = await own_company(db_session, "Other Co")
    jane = await repo.add(
        company_id, fields(linkedin_url="https://linkedin.com/in/jane-example"), source="typed"
    )
    await repo.add(
        other_id, fields(linkedin_url="https://linkedin.com/in/jane-example"), source="typed"
    )

    by_name = await repo.find_by_name_key(company_id, name_key("JANE  example"))
    by_link = await repo.find_by_link_key(company_id, link_key("linkedin.com/in/jane-example/"))

    assert by_name is not None
    assert by_name.id == jane.id
    assert by_link is not None
    assert by_link.id == jane.id
    assert await repo.find_by_name_key(company_id, "nobody") is None
    assert await repo.find_by_link_key(company_id, "linkedin.com/in/nobody") is None
    assert await repo.find_by_link_key(company_id, None) is None


async def test_repo_duplicate_name_key_is_refused(db_session: AsyncSession) -> None:
    repo = ContactsRepo(db_session)
    company_id = await own_company(db_session)
    await repo.add(company_id, fields("Jane Example"), source="typed")

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await repo.add(company_id, fields("jane  EXAMPLE"), source="typed")


async def test_repo_counts_per_company_in_one_query(db_session: AsyncSession) -> None:
    contacts = ContactsRepo(db_session)
    notes = NotesRepo(db_session)
    busy = await own_company(db_session, "Busy Co")
    noted = await own_company(db_session, "Noted Co")
    empty = await own_company(db_session, "Empty Co")
    await contacts.add(busy, fields("A One"), source="typed")
    await contacts.add(busy, fields("B Two"), source="typed")
    await notes.set(busy, "Called twice.", source="typed")
    await notes.set(noted, "Only a note.", source="import")

    statements: list[str] = []
    sync_engine = db_session.bind.sync_engine  # type: ignore[union-attr]

    def capture(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
        statements.append(statement)

    event.listen(sync_engine, "before_cursor_execute", capture)
    try:
        counts = await contacts.counts_by_company()
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture)

    assert counts[busy] == (2, True)
    assert counts[noted] == (0, True)
    assert counts[empty] == (0, False)
    assert len(statements) == 1


async def test_repo_note_upsert_and_delete_on_empty(db_session: AsyncSession) -> None:
    repo = NotesRepo(db_session)
    company_id = await own_company(db_session)
    assert await repo.get(company_id) is None

    await repo.set(company_id, "First note.", source="import")
    first = await repo.get(company_id)
    assert first is not None
    assert (first.body, first.source) == ("First note.", "import")

    await repo.set(company_id, "Edited by hand.", source="typed")
    second = await repo.get(company_id)
    assert second is not None
    assert (second.body, second.source) == ("Edited by hand.", "typed")
    assert await count(db_session, "company_notes") == 1

    await repo.set(company_id, None, source="typed")  # an empty note removes the row
    assert await repo.get(company_id) is None
    await repo.set(company_id, None, source="typed")  # and removing nothing is fine


# --- T007: wipe and seed paths already cover the new tables -----------------------------------

FIXTURES = Path(__file__).parents[2] / "fixtures" / "companies"


async def test_SC007_delete_all_removes_contacts_and_notes(db_session: AsyncSession) -> None:
    company_id = await own_company(db_session)
    await ContactsRepo(db_session).add(company_id, fields("Jane Example"), source="typed")
    await NotesRepo(db_session).set(company_id, "Private note.", source="typed")
    assert await count(db_session, "company_contacts") == 1

    await SqlDeleteAllStore(db_session).wipe_and_reseed()

    assert await count(db_session, "company_contacts") == 0
    assert await count(db_session, "company_notes") == 0
    assert await count(db_session, "companies") == 0


async def test_FR025_seed_update_keeps_contacts_attached(db_session: AsyncSession) -> None:
    companies = CompaniesRepo(db_session)
    await load_seed(companies, FIXTURES / "seed_v1.yaml")
    alpha = await companies.get_by_key("example-alpha")
    assert alpha is not None
    alpha_id = alpha.id
    contact = await ContactsRepo(db_session).add(alpha_id, fields("Jane Example"), source="typed")
    contact_id = contact.id

    await load_seed(companies, FIXTURES / "seed_v2.yaml")

    after = await companies.get_by_key("example-alpha")
    assert after is not None
    assert after.id == alpha_id  # the shipped list updates the row in place
    kept = await ContactsRepo(db_session).get(contact_id)
    assert kept is not None
    assert kept.company_id == alpha_id


async def test_FR021_seed_with_contacts_field_is_rejected(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "- key: example-alpha\n"
        "  name: Example Alpha\n"
        "  resolution: unresolved\n"
        "  seed_version: 1\n"
        "  contacts:\n"
        "    - name: Jane Example\n",
        encoding="utf-8",
    )

    with pytest.raises(SeedError, match="contacts"):
        await load_seed(CompaniesRepo(db_session), seed)
    assert await count(db_session, "companies") == 0
