"""T055: company CSV export and import (contracts/rest-api.md "Companies"; US3-AS6, R11)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.companies import SearchCompaniesApiDeps, create_companies_router
from hiretitan.search.infra.careerops.fake import FileCareerOps
from hiretitan.search.infra.models import CompanyRow
from hiretitan.search.infra.repos import CompaniesRepo

NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)
BASE = "/api/v1/companies"
HEADER = "name,city,website,careers_url,ats_vendor,board_id,hidden"


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    clock: FakeClock


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    clock = FakeClock(NOW)
    deps = SearchCompaniesApiDeps(sessions=sessions, clock=clock, careers=FileCareerOps(None))
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_companies_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions, clock)


async def add(env: Env, name: str, **fields: object) -> UUID:
    values: dict[str, object] = {"origin": "user", "resolution": "verified"} | fields
    async with env.sessions() as session:
        row = await CompaniesRepo(session).add(name=name, **values)
        await session.commit()
        return row.id


async def preview(env: Env, text: str | bytes) -> httpx.Response:
    data = text.encode() if isinstance(text, str) else text
    return await env.client.post(
        f"{BASE}/import", files={"file": ("companies.csv", data, "text/csv")}
    )


async def names(env: Env) -> list[str]:
    async with env.sessions() as session:
        rows = await session.scalars(select(CompanyRow).order_by(CompanyRow.name))
        return [r.name for r in rows]


def sheet(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


async def test_US3_AS6_preview_lists_add_update_invalid(env: Env) -> None:
    await add(env, "Acme", city="Pune", careers_url="https://acme.example.com/careers")
    csv = sheet(
        "Acme,Bengaluru,,https://acme.example.com/careers,,,",  # same company, new city
        "Brand New,Chennai,,https://new.example.com/jobs,,,",
        ",Pune,,,,,",  # no name
        "Odd,,,ftp://odd.example.com,,,",  # not a web link
        "Half,,,,lever,,",  # board without an id
    )

    response = await preview(env, csv)

    assert response.status_code == 200
    body = response.json()
    assert [r["name"] for r in body["add"]] == ["Brand New"]
    assert [(r["name"], r["changes"]) for r in body["update"]] == [
        ("Acme", {"city": {"from": "Pune", "to": "Bengaluru"}})
    ]
    assert [r["row"] for r in body["invalid"]] == [4, 5, 6]  # line numbers, header is line 1
    assert all(r["reason"] for r in body["invalid"])
    assert body["token"]


async def test_US3_AS6_nothing_changes_before_confirm(env: Env) -> None:
    await add(env, "Acme")

    await preview(env, sheet("Brand New,Chennai,,https://new.example.com/jobs,,,"))

    assert await names(env) == ["Acme"]


async def test_US3_AS6_confirm_applies_the_preview(env: Env) -> None:
    acme = await add(env, "Acme", city="Pune")
    token = (
        await preview(env, sheet("Acme,Bengaluru,,,,,", "Brand New,,,https://n.example.com,,,true"))
    ).json()["token"]

    response = await env.client.post(f"{BASE}/import/{token}/confirm")

    assert response.json() == {"added": 1, "updated": 1}
    async with env.sessions() as session:
        updated = await session.get(CompanyRow, acme)
        assert updated is not None
        assert updated.city == "Bengaluru"
        fresh = (
            await session.scalars(select(CompanyRow).where(CompanyRow.name == "Brand New"))
        ).one()
        assert (fresh.origin, fresh.hidden, fresh.resolution) == ("user", True, "careers_page")
    assert (await env.client.post(f"{BASE}/import/{token}/confirm")).status_code == 404  # used once


async def test_a_board_in_the_file_marks_the_company_confirmed(env: Env) -> None:
    token = (await preview(env, sheet("Acme,,,,greenhouse,acme,"))).json()["token"]

    await env.client.post(f"{BASE}/import/{token}/confirm")

    async with env.sessions() as session:
        row = (await session.scalars(select(CompanyRow))).one()
        assert (row.ats_vendor, row.board_id, row.resolution) == (
            "greenhouse",
            "acme",
            "user_confirmed",
        )


async def test_editing_a_built_in_company_marks_it_edited(env: Env) -> None:
    built_in = await add(env, "Acme", origin="built_in", key="acme", city="Pune")
    token = (await preview(env, sheet("Acme,Bengaluru,,,,,"))).json()["token"]

    await env.client.post(f"{BASE}/import/{token}/confirm")

    async with env.sessions() as session:
        row = await session.get(CompanyRow, built_in)
        assert row is not None
        assert row.user_modified is True


async def test_an_empty_cell_leaves_the_value_alone(env: Env) -> None:
    await add(env, "Acme", city="Pune", website="https://acme.example.com")

    body = (await preview(env, sheet("Acme,,,,,,"))).json()

    assert body["update"] == []
    assert body["add"] == []


async def test_a_name_twice_in_the_file_is_listed_once_and_flagged(env: Env) -> None:
    body = (await preview(env, sheet("Acme,,,,,,", "acme,,,,,,"))).json()

    assert [r["name"] for r in body["add"]] == ["Acme"]
    assert [r["row"] for r in body["invalid"]] == [3]


async def test_the_same_name_on_another_site_is_another_company(env: Env) -> None:
    await add(env, "Acme", careers_url="https://acme.example.com/careers")

    body = (await preview(env, sheet("Acme,,,https://acme.example.org/jobs,,,"))).json()

    assert [r["name"] for r in body["add"]] == ["Acme"]


async def test_R11_export_roundtrips_through_import(env: Env) -> None:
    await add(
        env,
        "Acme, Inc.",
        city="Pune",
        website="https://acme.example.com",
        careers_url="https://acme.example.com/careers",
        ats_vendor="lever",
        board_id="acme",
    )
    await add(env, "Quiet", hidden=True, resolution="check_manually")
    gone = await add(env, "Gone")
    async with env.sessions() as session:
        await CompaniesRepo(session).set_fields(gone, deleted_at=NOW)
        await session.commit()

    exported = await env.client.get(f"{BASE}/export")

    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "attachment" in exported.headers["content-disposition"]
    assert exported.text.splitlines()[0] == HEADER
    assert "Gone" not in exported.text
    body = (await preview(env, exported.text)).json()
    assert (body["add"], body["update"], body["invalid"]) == ([], [], [])


async def test_a_spreadsheet_formula_in_a_cell_is_neutralised_and_restored(env: Env) -> None:
    await add(env, "=SUM(A1)")

    exported = (await env.client.get(f"{BASE}/export")).text

    assert "'=SUM(A1)" in exported
    body = (await preview(env, exported)).json()
    assert (body["add"], body["update"], body["invalid"]) == ([], [], [])


async def test_R11_file_limits(env: Env) -> None:
    too_big = await preview(env, "name\n" + "x" * 1_100_000)
    too_many = await preview(env, "name\n" + "\n".join(f"Co {i}" for i in range(2001)))
    at_limit = await preview(env, "name\n" + "\n".join(f"Co {i}" for i in range(2000)))
    not_csv = await preview(env, b"\xff\xfe\x00\x01 binary")
    no_name = await preview(env, "city,website\nPune,\n")

    assert too_big.status_code == 413
    assert too_many.status_code == 422
    assert "2,000" in too_many.json()["detail"]
    assert at_limit.status_code == 200
    assert len(at_limit.json()["add"]) == 2000
    assert not_csv.status_code == 422
    assert no_name.status_code == 422
    assert "name" in no_name.json()["detail"]


async def test_an_old_preview_cannot_be_confirmed(env: Env) -> None:
    token = (await preview(env, sheet("Acme,,,,,,"))).json()["token"]
    env.clock.advance(timedelta(hours=2))

    response = await env.client.post(f"{BASE}/import/{token}/confirm")

    assert response.status_code == 404
    assert await names(env) == []
