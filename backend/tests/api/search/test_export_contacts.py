"""T024: the company export with and without contacts (US4 AS2, AS3; FR-021, FR-024)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.companies import SearchCompaniesApiDeps, create_companies_router
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.careerops.fake import FileCareerOps
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, NotesRepo

NOW = datetime(2026, 11, 11, 9, tzinfo=UTC)
BASE = "/api/v1/companies"
MARKERS = ("Jane Marker", "jane.marker@example.org", "+91 90000 11111", "marker note text")


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    deps = SearchCompaniesApiDeps(
        sessions=sessions, clock=FakeClock(NOW), careers=FileCareerOps(None)
    )
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_companies_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions)


async def company(env: Env, name: str) -> UUID:
    async with env.sessions() as session:
        row = await CompaniesRepo(session).add(
            name=name, origin="user", resolution="verified", city="Pune"
        )
        await session.commit()
        return row.id


async def person(env: Env, company_id: UUID, **fields: str | None) -> None:
    async with env.sessions() as session:
        await ContactsRepo(session).add(company_id, ContactFields(**fields), source="typed")  # type: ignore[arg-type]
        await session.commit()


async def note(env: Env, company_id: UUID, body: str) -> None:
    async with env.sessions() as session:
        await NotesRepo(session).set(company_id, body, source="typed")
        await session.commit()


async def seed_marked(env: Env) -> UUID:
    acme = await company(env, "Acme")
    await person(
        env,
        acme,
        name="Jane Marker",
        role="Recruiter",
        linkedin_url="https://www.linkedin.com/in/jane-marker",
        email="jane.marker@example.org",
        phone="+91 90000 11111",
        confidence="high",
        note="Replies fast.",
    )
    await note(env, acme, "marker note text")
    return acme


async def test_US4_AS2_default_export_has_no_contact_fields(env: Env) -> None:
    await seed_marked(env)

    body = (await env.client.get(f"{BASE}/export")).text

    header = body.splitlines()[0].split(",")
    assert "contacts" not in header
    assert "notes" not in header
    for marker in (*MARKERS, "linkedin.com/in/jane-marker"):
        assert marker not in body


async def test_US4_AS2_an_explicit_false_is_the_default(env: Env) -> None:
    await seed_marked(env)

    body = (await env.client.get(f"{BASE}/export", params={"include_contacts": "false"})).text

    assert "Jane Marker" not in body


async def test_US4_AS3_opt_in_export_round_trips_through_sheet_import(env: Env) -> None:
    await seed_marked(env)
    await company(env, "Quiet Co")  # no contacts, no note
    exported = await env.client.get(f"{BASE}/export", params={"include_contacts": "true"})
    assert exported.status_code == 200
    assert exported.text.splitlines()[0].endswith(",contacts,notes")
    for marker in MARKERS:
        assert marker in exported.text

    async with env.sessions() as session:  # a fresh install: everything the person owns is gone
        await session.execute(
            text("TRUNCATE app.company_contacts, app.company_notes, app.companies CASCADE")
        )
        await session.commit()

    uploaded = await env.client.post(
        f"{BASE}/sheet-import",
        files={"file": ("export.csv", exported.text.encode(), "text/csv")},
    )
    assert uploaded.status_code == 200
    confirmed = await env.client.post(f"{BASE}/sheet-import/{uploaded.json()['token']}/confirm")
    assert confirmed.status_code == 200

    async with env.sessions() as session:
        acme = next(c for c in await CompaniesRepo(session).list_all() if c.name == "Acme")
        [contact] = await ContactsRepo(session).list_for_company(acme.id)
        stored_note = await NotesRepo(session).get(acme.id)
    assert (contact.name, contact.role, contact.confidence) == ("Jane Marker", "Recruiter", "high")
    assert contact.linkedin_url == "https://www.linkedin.com/in/jane-marker"
    assert (contact.email, contact.phone) == ("jane.marker@example.org", "+91 90000 11111")
    assert contact.note == "Replies fast."
    assert stored_note is not None
    assert stored_note.body == "marker note text"


async def test_formula_cells_in_contacts_are_escaped(env: Env) -> None:
    acme = await company(env, "Acme")
    await person(env, acme, name="=HYPERLINK(1)", role="Recruiter")
    await note(env, acme, "-2+3 is a formula to a spreadsheet")

    body = (await env.client.get(f"{BASE}/export", params={"include_contacts": "true"})).text

    assert "'=HYPERLINK(1)" in body
    assert "'-2+3" in body
    assert ",=HYPERLINK" not in body
    assert ',"=HYPERLINK' not in body


async def test_002_import_of_an_export_with_contacts_ignores_the_extra_columns(env: Env) -> None:
    await seed_marked(env)
    exported = (await env.client.get(f"{BASE}/export", params={"include_contacts": "true"})).text

    response = await env.client.post(
        f"{BASE}/import", files={"file": ("export.csv", exported.encode(), "text/csv")}
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["add"], body["update"], body["invalid"]) == ([], [], [])
