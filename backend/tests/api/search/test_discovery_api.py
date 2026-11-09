"""T050: add a company and confirm its board over the API (contracts/rest-api.md, "Companies";
US3-AS2, FR-017)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.companies import SearchCompaniesApiDeps, create_companies_router
from hiretitan.search.application.ports import (
    BoardRef,
    DiscoveryResult,
    Posting,
    ScanOk,
    ScanResult,
)
from hiretitan.search.infra.careerops.boards import discover_board

NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)
BASE = "/api/v1/companies"


class StubCareerOps:
    def __init__(self) -> None:
        self.unsupported = False
        self.scanned: list[BoardRef] = []

    async def scan(self, refs: list[BoardRef]) -> ScanResult:
        self.scanned += refs
        return {r.company_id: ScanOk([Posting("A", "https://x.example/a")] * 4) for r in refs}

    async def discover(self, careers_url: str) -> DiscoveryResult | None:
        if self.unsupported:
            return DiscoveryResult("smartrecruiters", "acme")
        return discover_board(careers_url)


@dataclass
class Env:
    client: httpx.AsyncClient
    careers: StubCareerOps


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    careers = StubCareerOps()
    deps = SearchCompaniesApiDeps(sessions=sessions, clock=FakeClock(NOW), careers=careers)
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_companies_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, careers)


async def add(env: Env, **changes: str) -> dict[str, Any]:
    body = {
        "name": "Acme",
        "careers_url": "https://job-boards.greenhouse.io/acme",
        "city": "Pune",
    } | changes
    response = await env.client.post(BASE, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_post_creates_an_unresolved_company_the_person_owns(env: Env) -> None:
    company = await add(env)

    assert (company["name"], company["origin"], company["resolution"]) == (
        "Acme",
        "user",
        "unresolved",
    )
    assert (company["board_status"], company["city"]) == ("unresolved", "Pune")
    assert company["ats_vendor"] is None


async def test_post_with_missing_or_bad_fields_is_422(env: Env) -> None:
    response = await env.client.post(BASE, json={"name": "", "careers_url": ""})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["name", "careers_url"]
    assert (await env.client.get(BASE)).json()["items"] == []

    bad = await env.client.post(BASE, json={"name": "Acme", "careers_url": "nope"})
    assert [e["field"] for e in bad.json()["errors"]] == ["careers_url"]


async def test_US3_AS2_match_used_only_after_confirm(env: Env) -> None:
    company = await add(env)
    cid = company["id"]

    found = await env.client.get(f"{BASE}/{cid}/discovery")

    assert found.status_code == 200
    assert found.json() == {
        "status": "found",
        "suggestion": {
            "ats_vendor": "greenhouse",
            "board_id": "acme",
            "supported": True,
            "live_jobs": 4,
        },
    }
    still = next(c for c in (await env.client.get(BASE)).json()["items"] if c["id"] == cid)
    assert (still["ats_vendor"], still["board_status"]) == (None, "unresolved")

    confirmed = await env.client.post(f"{BASE}/{cid}/discovery/confirm")

    assert confirmed.status_code == 200
    body = confirmed.json()
    assert (body["ats_vendor"], body["board_id"], body["resolution"]) == (
        "greenhouse",
        "acme",
        "user_confirmed",
    )
    assert body["board_status"] == "board"


async def test_no_match_has_nothing_to_confirm(env: Env) -> None:
    company = await add(env, careers_url="https://www.example.com/careers")
    cid = company["id"]

    found = await env.client.get(f"{BASE}/{cid}/discovery")
    assert found.json() == {"status": "none", "suggestion": None}

    confirm = await env.client.post(f"{BASE}/{cid}/discovery/confirm")
    assert confirm.status_code == 409
    assert confirm.json()["reason"] == "no_board"


async def test_reject_falls_back_to_the_careers_page(env: Env) -> None:
    company = await add(env)

    rejected = await env.client.post(f"{BASE}/{company['id']}/discovery/reject")

    assert rejected.status_code == 200
    assert (rejected.json()["resolution"], rejected.json()["board_status"]) == (
        "careers_page",
        "careers_page",
    )
    assert rejected.json()["ats_vendor"] is None


async def test_unsupported_vendor_is_shown_and_falls_back_to_check_manually(env: Env) -> None:
    env.careers.unsupported = True
    company = await add(env)
    cid = company["id"]

    found = (await env.client.get(f"{BASE}/{cid}/discovery")).json()
    assert found["status"] == "unsupported"
    assert found["suggestion"]["supported"] is False
    assert env.careers.scanned == []
    assert (await env.client.post(f"{BASE}/{cid}/discovery/confirm")).status_code == 409

    rejected = (await env.client.post(f"{BASE}/{cid}/discovery/reject")).json()
    assert rejected["board_status"] == "check_manually"
    manual = (await env.client.get(BASE, params={"filter": "check_manually"})).json()["items"]
    assert [c["id"] for c in manual] == [cid]


async def test_an_unknown_company_is_404(env: Env) -> None:
    missing = UUID(int=11)

    for method, path in (
        ("GET", f"{BASE}/{missing}/discovery"),
        ("POST", f"{BASE}/{missing}/discovery/confirm"),
        ("POST", f"{BASE}/{missing}/discovery/reject"),
    ):
        assert (await env.client.request(method, path)).status_code == 404
