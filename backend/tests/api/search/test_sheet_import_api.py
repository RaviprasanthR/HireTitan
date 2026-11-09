"""T012: the sheet import endpoints (contracts/rest-api.md "Sheet import"; US1, SC-001..3)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.companies import SearchCompaniesApiDeps, create_companies_router
from hiretitan.search.application.seed import load_seed
from hiretitan.search.infra.careerops.fake import FileCareerOps
from hiretitan.search.infra.repos import CompaniesRepo

NOW = datetime(2026, 11, 9, 9, tzinfo=UTC)
BASE = "/api/v1/companies"
FIXTURES = Path(__file__).parents[2] / "fixtures"
SAMPLE = (FIXTURES / "sheets" / "product_companies_sample.csv").read_bytes()


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    clock: FakeClock


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    async with sessions() as session:
        await load_seed(CompaniesRepo(session), FIXTURES / "companies" / "seed_v1.yaml")
        await session.commit()
    clock = FakeClock(NOW)
    deps = SearchCompaniesApiDeps(sessions=sessions, clock=clock, careers=FileCareerOps(None))
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_companies_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions, clock)


async def upload(
    env: Env, data: str | bytes, filename: str = "sheet.csv", path: str = "sheet-import"
) -> httpx.Response:
    body = data.encode() if isinstance(data, str) else data
    return await env.client.post(f"{BASE}/{path}", files={"file": (filename, body, "text/csv")})


async def count(env: Env, table: str) -> int:
    async with env.sessions() as session:
        return int((await session.execute(text(f"SELECT count(*) FROM app.{table}"))).scalar_one())


async def test_US1_AS6_result_counts(env: Env) -> None:
    preview = await upload(env, SAMPLE)

    assert preview.status_code == 200
    body = preview.json()
    assert body["companies"] == {"matched": 3, "to_add": 8}
    assert body["contacts"] == {"to_add": 30, "to_update": 0}
    assert body["notes"]["to_set"] >= 1
    assert set(body["columns"]["used"]) == {
        "name",
        "location",
        "website",
        "careers",
        "contacts",
        "notes",
    }
    assert "Frontend openings" in body["columns"]["ignored"]
    assert await count(env, "company_contacts") == 0  # nothing is saved by a preview

    confirm = await env.client.post(f"{BASE}/sheet-import/{body['token']}/confirm")

    assert confirm.status_code == 200
    result = confirm.json()
    assert result["matched"] == 3
    assert result["companies_added"] == 8
    assert result["contacts_added"] == 30
    assert result["contacts_updated"] == 0
    assert result["notes_set"] == body["notes"]["to_set"]
    assert len(result["skipped"]) == 2
    assert await count(env, "company_contacts") == 30
    assert await count(env, "companies") == 3 + 8


async def test_US1_AS4_skipped_rows_listed_with_reason(env: Env) -> None:
    body = (await upload(env, SAMPLE)).json()

    skipped = {s["line"]: s["reason"] for s in body["skipped"]}

    assert len(skipped) == 2
    assert any("no company name" in r.lower() for r in skipped.values())
    assert any("Example Alpha" in r and "Example Beta" in r for r in skipped.values())
    assert any("20" in s["reason"] for s in body["shortened"])


async def test_SC003_every_skipped_row_is_reported(env: Env) -> None:
    body = (await upload(env, SAMPLE)).json()

    rows_in = len(body["rows"])
    skipped = len(body["skipped"])

    assert rows_in == 13
    assert body["companies"]["matched"] + body["companies"]["to_add"] + skipped == rows_in
    assert sum(r["action"] == "skip" for r in body["rows"]) == skipped


async def test_FR001_wrong_file_type_is_refused_before_saving(env: Env) -> None:
    not_csv_name = await upload(env, SAMPLE, filename="sheet.xlsx")
    binary = await upload(env, b"PK\x03\x04\x00\x00 binary", filename="sheet.csv")

    assert not_csv_name.status_code == 415
    assert binary.status_code == 415
    assert await count(env, "company_contacts") == 0
    assert await count(env, "companies") == 3


async def test_FR001_over_1mb_is_413(env: Env) -> None:
    response = await upload(env, "Company,City\n" + "x" * 1_100_000)

    assert response.status_code == 413


async def test_FR001_over_2000_rows_is_422(env: Env) -> None:
    rows = "\n".join(f"Co {i},Pune" for i in range(2001))
    at_limit = "\n".join(f"Co {i},Pune" for i in range(2000))

    too_many = await upload(env, "Company,City\n" + rows)
    ok = await upload(env, "Company,City\n" + at_limit)

    assert too_many.status_code == 422
    assert "2,000" in too_many.json()["detail"]
    assert ok.status_code == 200


async def test_FR001_no_name_column_is_422_with_headers_seen(env: Env) -> None:
    response = await upload(env, (FIXTURES / "sheets" / "not_a_sheet.csv").read_bytes())

    assert response.status_code == 422
    body = response.json()
    assert "company name" in body["detail"]
    assert body["headers"] == ["Project", "Owner", "Budget"]


async def test_preview_expires_after_30_minutes_is_404(env: Env) -> None:
    token = (await upload(env, SAMPLE)).json()["token"]
    env.clock.advance(timedelta(minutes=31))

    response = await env.client.post(f"{BASE}/sheet-import/{token}/confirm")

    assert response.status_code == 404
    assert await count(env, "company_contacts") == 0


async def test_a_company_csv_preview_token_is_not_a_sheet_token(env: Env) -> None:
    csv_preview = await env.client.post(
        f"{BASE}/import", files={"file": ("c.csv", b"name\nAcme\n", "text/csv")}
    )
    token = csv_preview.json()["token"]

    response = await env.client.post(f"{BASE}/sheet-import/{token}/confirm")

    assert response.status_code == 404


async def test_SC002_reimport_preview_has_nothing_to_do(env: Env) -> None:
    first = (await upload(env, SAMPLE)).json()["token"]
    await env.client.post(f"{BASE}/sheet-import/{first}/confirm")

    again = (await upload(env, SAMPLE)).json()

    assert again["companies"]["to_add"] == 0
    assert again["contacts"] == {"to_add": 0, "to_update": 0}
    assert again["notes"]["to_set"] == 0
    assert again["notes"]["to_change"] == 0


async def test_SC001_sixty_two_rows_under_ten_seconds(env: Env) -> None:
    header = "Org Name,Location,Company site,HR / LinkedIn contacts,Notes\n"
    rows = []
    for i in range(62):
        lines = [
            f"Person{i}A Example - Recruiter [High]",
            f"https://www.linkedin.com/in/p{i}a",
            f"Person{i}B Example",
        ]
        cell = '"' + "\n".join(lines) + '"'
        rows.append(f"Sample Co {i},Pune,https://co{i}.example.test,{cell},Note {i}")
    started = time.perf_counter()

    preview = await upload(env, header + "\n".join(rows))
    confirm = await env.client.post(f"{BASE}/sheet-import/{preview.json()['token']}/confirm")

    assert time.perf_counter() - started < 10
    assert confirm.json()["contacts_added"] == 124
    assert confirm.json()["companies_added"] == 62
