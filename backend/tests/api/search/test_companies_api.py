"""T049: the companies endpoints (contracts/rest-api.md, "Companies"; US3, FR-016 to FR-019)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.companies import SearchCompaniesApiDeps, create_companies_router
from hiretitan.search.infra.careerops.fake import FileCareerOps
from hiretitan.search.infra.repos import CompaniesRepo

NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)
BASE = "/api/v1/companies"


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


async def add(env: Env, name: str, **fields: object) -> UUID:
    values: dict[str, object] = {"origin": "user", "resolution": "verified"} | fields
    async with env.sessions() as session:
        row = await CompaniesRepo(session).add(name=name, **values)
        await session.commit()
        return row.id


async def test_US3_AS1_lists_companies_with_board_status(env: Env) -> None:
    await add(env, "Acme", origin="built_in", key="acme", ats_vendor="greenhouse", board_id="acme")
    await add(env, "Keka Co", resolution="check_manually")

    page = (await env.client.get(BASE)).json()

    assert [c["name"] for c in page["items"]] == ["Acme", "Keka Co"]
    assert page["next_cursor"] is None
    acme = page["items"][0]
    assert (acme["board_status"], acme["origin"], acme["hidden"]) == ("board", "built_in", False)
    assert page["items"][1]["board_status"] == "check_manually"


async def test_the_filters(env: Env) -> None:
    await add(env, "Visible")
    await add(env, "Quiet", hidden=True)
    await add(env, "Manual", resolution="check_manually")

    def names(page: httpx.Response) -> list[str]:
        return [c["name"] for c in page.json()["items"]]

    assert names(await env.client.get(BASE, params={"filter": "all"})) == [
        "Manual",
        "Quiet",
        "Visible",
    ]
    assert names(await env.client.get(BASE, params={"filter": "hidden"})) == ["Quiet"]
    assert names(await env.client.get(BASE, params={"filter": "check_manually"})) == ["Manual"]
    assert (await env.client.get(BASE, params={"filter": "nope"})).status_code == 422


async def test_US3_AS4_hide_and_unhide(env: Env) -> None:
    company = await add(env, "Acme", ats_vendor="lever", board_id="acme")

    hidden = await env.client.patch(f"{BASE}/{company}", json={"hidden": True})

    assert hidden.status_code == 200
    assert (hidden.json()["hidden"], hidden.json()["user_modified"]) == (True, False)
    shown = await env.client.patch(f"{BASE}/{company}", json={"hidden": False})
    assert shown.json()["hidden"] is False


async def test_FR018_edit_sets_user_modified(env: Env) -> None:
    company = await add(env, "Acme", origin="built_in", key="acme", city="Pune")

    response = await env.client.patch(
        f"{BASE}/{company}",
        json={"name": "Acme Labs", "city": "", "careers_url": "https://acme.example.com/jobs"},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["city"], body["user_modified"]) == ("Acme Labs", None, True)
    assert body["careers_url"] == "https://acme.example.com/jobs"


async def test_an_invalid_edit_is_422_with_field_errors_and_changes_nothing(env: Env) -> None:
    company = await add(env, "Acme")

    response = await env.client.patch(
        f"{BASE}/{company}", json={"name": "", "website": "not a link"}
    )

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["name", "website"]
    listed = (await env.client.get(BASE)).json()["items"][0]
    assert (listed["name"], listed["user_modified"]) == ("Acme", False)


async def test_an_unknown_company_is_404(env: Env) -> None:
    missing = UUID(int=7)

    assert (await env.client.patch(f"{BASE}/{missing}", json={"hidden": True})).status_code == 404
    assert (await env.client.delete(f"{BASE}/{missing}")).status_code == 404


async def test_FR016_delete_removes_a_user_company_and_tombstones_a_built_in_one(env: Env) -> None:
    mine = await add(env, "Mine")
    shipped = await add(env, "Shipped", origin="built_in", key="shipped")

    assert (await env.client.delete(f"{BASE}/{mine}")).status_code == 204
    assert (await env.client.delete(f"{BASE}/{shipped}")).status_code == 204

    assert (await env.client.get(BASE)).json()["items"] == []
    async with env.sessions() as session:
        assert await CompaniesRepo(session).get(mine) is None
        tombstone = await CompaniesRepo(session).get(shipped)
        assert tombstone is not None
        assert tombstone.deleted_at == NOW
    assert (await env.client.delete(f"{BASE}/{shipped}")).status_code == 404


# --- feature 002b (T015): contact count, note flag and the openings placeholder ---------------


async def test_US2_AS1_company_row_has_contact_count_and_note_flag(env: Env) -> None:
    from hiretitan.search.domain.contacts import ContactFields
    from hiretitan.search.infra.repos import ContactsRepo, NotesRepo

    busy = await add(env, "Busy Co")
    await add(env, "Quiet Co")
    noted = await add(env, "Noted Co")
    async with env.sessions() as session:
        contacts = ContactsRepo(session)
        await contacts.add(busy, ContactFields(name="Jane Example"), source="typed")
        await contacts.add(busy, ContactFields(name="John Sample"), source="import")
        await NotesRepo(session).set(noted, "Spoke to HR.", source="typed")
        await session.commit()

    page = (await env.client.get(BASE)).json()

    rows = {c["name"]: c for c in page["items"]}
    assert (rows["Busy Co"]["contact_count"], rows["Busy Co"]["has_note"]) == (2, False)
    assert (rows["Quiet Co"]["contact_count"], rows["Quiet Co"]["has_note"]) == (0, False)
    assert (rows["Noted Co"]["contact_count"], rows["Noted Co"]["has_note"]) == (0, True)


async def test_company_row_has_a_short_one_line_note_preview(env: Env) -> None:
    from hiretitan.search.infra.repos import NotesRepo

    long_note = "Spoke to HR on Monday.\n\nShe said   to apply " + "again soon " * 30
    short, long, none = (
        await add(env, "Short Co"),
        await add(env, "Long Co"),
        await add(env, "None Co"),
    )
    async with env.sessions() as session:
        await NotesRepo(session).set(short, "Call back  Friday", source="typed")
        await NotesRepo(session).set(long, long_note, source="typed")
        await session.commit()

    rows = {c["name"]: c for c in (await env.client.get(BASE)).json()["items"]}

    assert rows["Short Co"]["note_preview"] == "Call back Friday"
    preview = rows["Long Co"]["note_preview"]
    assert preview.startswith("Spoke to HR on Monday. She said to apply again soon")
    assert len(preview) <= 120
    assert preview.endswith("…")
    assert "\n" not in preview
    assert rows["None Co"]["note_preview"] is None
    assert none  # the company exists


async def test_companies_list_runs_a_fixed_number_of_queries(env: Env) -> None:
    from sqlalchemy import event

    from hiretitan.search.domain.contacts import ContactFields
    from hiretitan.search.infra.repos import ContactsRepo

    engine = env.sessions.kw["bind"].sync_engine
    statements: list[str] = []

    def capture(conn: object, cursor: object, statement: str, *rest: object) -> None:
        statements.append(statement)

    async def run_list() -> int:
        statements.clear()
        event.listen(engine, "before_cursor_execute", capture)
        try:
            assert (await env.client.get(BASE)).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        return len(statements)

    for i in range(3):
        await add(env, f"Small {i}")
    few = await run_list()

    for i in range(30):
        company = await add(env, f"Large {i}")
        async with env.sessions() as session:
            await ContactsRepo(session).add(company, ContactFields(name="Jane"), source="typed")
            await session.commit()
    many = await run_list()

    assert few == many  # no query per company


# --- the list says whether the person has an application at each company ---------------------


async def _job(env: Env, company: UUID, title: str, state: str) -> None:
    from datetime import date

    from hiretitan.search.infra.repos import JobsRepo

    async with env.sessions() as session:
        await JobsRepo(session).add(
            company_id=company,
            company_name="x",
            title=title,
            description="text",
            state=state,
            applied_on=date(2026, 11, 3) if state == "applied" else None,
            inquired_on=date(2026, 11, 2) if state == "inquired" else None,
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        await session.commit()


async def test_FR009_company_pipeline_is_applied_inquired_or_null(env: Env) -> None:
    applied = await add(env, "Applied Co")
    asked = await add(env, "Asked Co")
    both = await add(env, "Both Co")
    browsing = await add(env, "Browsing Co")
    await add(env, "Nothing Co")
    await _job(env, applied, "Backend Engineer", "applied")
    await _job(env, applied, "Frontend Engineer", "explore")
    await _job(env, asked, "Backend Engineer", "inquired")
    await _job(env, both, "Backend Engineer", "inquired")
    await _job(env, both, "Platform Engineer", "applied")  # applied wins over inquired
    await _job(env, browsing, "Backend Engineer", "explore")
    await _job(env, browsing, "QA Engineer", "skipped")

    rows = {c["name"]: c for c in (await env.client.get(BASE)).json()["items"]}

    assert rows["Applied Co"]["pipeline"] == "applied"
    assert rows["Asked Co"]["pipeline"] == "inquired"
    assert rows["Both Co"]["pipeline"] == "applied"
    assert rows["Browsing Co"]["pipeline"] is None  # looking at jobs is not applying
    assert rows["Nothing Co"]["pipeline"] is None
    assert "has_application" not in rows["Nothing Co"]


async def test_the_list_no_longer_carries_open_role_counts(env: Env) -> None:
    await add(env, "Any Co")

    (row,) = (await env.client.get(BASE)).json()["items"]

    assert "openings" not in row
