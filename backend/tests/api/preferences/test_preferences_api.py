"""T054: the preferences endpoints (contracts/rest-api.md, "Preferences")."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.preferences.api.router import PreferencesApiDeps, create_preferences_router
from hiretitan.profile.domain.content import Contact, Experience, ProfileContent, YearMonth
from hiretitan.profile.infra.repos import VersionsRepo


def body(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "target_roles": ["Backend Engineer"],
        "seniority_levels": ["senior"],
        "years_experience": "6.5",
        "key_skills": ["Python"],
        "preferred_locations": [{"city": "Pune", "country": "IN"}],
        "default_country": "IN",
        "work_modes": ["remote", "hybrid"],
        "willing_to_relocate": False,
        "blocked_locations": [],
        "job_types": ["full_time"],
        "pay": {
            "currency": "INR",
            "min_annual": "1800000",
            "target_annual": "2400000",
            "basis": "fixed",
        },
        "notice_period_days": 30,
        "earliest_start_date": None,
        "preferred_companies": [],
        "avoided_companies": [],
    }
    return {**base, **changes}


@pytest.fixture
async def client(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path, fake_clock: FakeClock
) -> AsyncIterator[httpx.AsyncClient]:
    deps = PreferencesApiDeps(sessions=sessions, clock=fake_clock, profile_reader=VersionsRepo)
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_preferences_router(deps)]
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_defaults_before_first_save(client: httpx.AsyncClient) -> None:
    res = await client.get("/api/v1/preferences")
    assert res.status_code == 200
    data = res.json()
    assert data["saved_at"] is None
    assert data["content"]["default_country"] == "IN"
    assert data["content"]["pay"]["currency"] == "INR"
    assert sorted(data["content"]["work_modes"]) == ["hybrid", "onsite", "remote"]
    assert data["suggestions"] == {"target_roles": [], "key_skills": []}


async def test_US2_AS2_put_then_get_roundtrip(client: httpx.AsyncClient) -> None:
    put = await client.put("/api/v1/preferences", json=body())
    assert put.status_code == 200
    saved_at = put.json()["saved_at"]
    assert saved_at.startswith("2026-11-04T09:00:00")

    got = (await client.get("/api/v1/preferences")).json()
    assert got["saved_at"] == saved_at
    content = got["content"]
    assert content["target_roles"] == ["Backend Engineer"]
    assert content["years_experience"] == "6.5"
    assert content["pay"]["min_annual"] == "1800000"
    assert sorted(content["work_modes"]) == ["hybrid", "remote"]
    assert content["preferred_locations"] == [{"city": "Pune", "country": "IN"}]


async def test_US2_AS4_field_errors_problem_json(client: httpx.AsyncClient) -> None:
    bad = body(
        target_roles=[],
        pay={"currency": "INR", "min_annual": "5", "target_annual": "1", "basis": "fixed"},
        years_experience="-1",
    )
    res = await client.put("/api/v1/preferences", json=bad)
    assert res.status_code == 422
    assert res.headers["content-type"].startswith("application/problem+json")
    fields = {e["field"] for e in res.json()["errors"]}
    assert fields == {"target_roles", "pay.min_annual", "years_experience"}
    assert (await client.get("/api/v1/preferences")).json()["saved_at"] is None  # nothing saved


async def test_wrong_types_are_field_errors_too(client: httpx.AsyncClient) -> None:
    res = await client.put("/api/v1/preferences", json=body(notice_period_days="soon"))
    assert res.status_code == 422
    assert [e["field"] for e in res.json()["errors"]] == ["notice_period_days"]


async def test_suggestions_come_from_the_profile(
    client: httpx.AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    job = Experience(
        employer="Acme", title="Platform Engineer", start=YearMonth(2020, 1), current=True
    )
    profile = ProfileContent(
        contact=Contact(name="Jane"), experience=(job,), skills=("Go", "Python")
    )
    async with sessions() as session:
        await VersionsRepo(session).create_version(profile, created_by="manual")
        await session.commit()
    await client.put("/api/v1/preferences", json=body())

    got = (await client.get("/api/v1/preferences")).json()

    assert got["suggestions"] == {"target_roles": ["Platform Engineer"], "key_skills": ["Go"]}
    assert got["content"]["key_skills"] == ["Python"]  # not added automatically


async def test_FR026_works_with_ai_key_missing(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert (await client.put("/api/v1/preferences", json=body())).status_code == 200
    assert (await client.get("/api/v1/preferences")).status_code == 200
