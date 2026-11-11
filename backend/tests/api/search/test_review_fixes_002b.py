"""Fixes from the Phase 3-6 reviews (python/FastAPI, security, database) of feature 002b."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.companies import SearchCompaniesApiDeps, create_companies_router
from hiretitan.search.api.contacts import SearchContactsApiDeps, create_contacts_router
from hiretitan.search.application.companies_csv import export_csv
from hiretitan.search.infra.careerops.fake import FileCareerOps
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo

NOW = datetime(2026, 11, 11, 9, tzinfo=UTC)
BASE = "/api/v1/companies"
SHEET = "Org Name,Location,Contacts\nAcme,Pune,Jane Example - Recruiter\n"
CSV = "name,city\nAcme,Pune\n"


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_companies_router(
                SearchCompaniesApiDeps(
                    sessions=sessions, clock=FakeClock(NOW), careers=FileCareerOps(None)
                )
            ),
            create_contacts_router(SearchContactsApiDeps(sessions=sessions)),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions)


async def upload(env: Env, path: str, body: str) -> httpx.Response:
    return await env.client.post(f"{BASE}/{path}", files={"file": ("f.csv", body.encode())})


async def test_an_expired_preview_has_a_machine_readable_code(env: Env) -> None:
    for tail in ("import/nope/confirm", "sheet-import/nope/confirm"):
        response = await env.client.post(f"{BASE}/{tail}")

        assert response.status_code == 404
        assert response.json()["code"] == "preview_expired"


async def test_a_token_of_the_other_kind_is_not_used_up(env: Env) -> None:
    token = (await upload(env, "sheet-import", SHEET)).json()["token"]

    wrong = await env.client.post(f"{BASE}/import/{token}/confirm")
    right = await env.client.post(f"{BASE}/sheet-import/{token}/confirm")

    assert wrong.status_code == 404
    assert right.status_code == 200  # the sheet preview was still there


async def test_a_confirmed_preview_is_used_once(env: Env) -> None:
    token = (await upload(env, "import", CSV)).json()["token"]

    first = await env.client.post(f"{BASE}/import/{token}/confirm")
    second = await env.client.post(f"{BASE}/import/{token}/confirm")

    assert first.status_code == 200
    assert second.status_code == 404


@pytest.mark.parametrize("path", ["import", "sheet-import"])
async def test_one_huge_cell_is_a_422_not_a_500(env: Env, path: str) -> None:
    huge = "name,notes\nAcme," + "x" * 200_000 + "\n"

    response = await upload(env, path, huge)

    assert response.status_code == 422


def test_a_leading_tab_or_return_is_neutralised_in_the_export() -> None:
    rows = [
        SimpleNamespace(
            id=uuid4(),
            name="\t=1+1",
            city="\r@x",
            website=None,
            careers_url=None,
            ats_vendor=None,
            board_id=None,
            hidden=False,
        )
    ]

    body = export_csv(rows)  # type: ignore[arg-type]

    assert "'\t=1+1" in body
    assert "'\r@x" in body


async def test_two_contacts_with_one_name_at_once_is_a_409_not_a_500(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with env.sessions() as session:
        company: UUID = (
            await CompaniesRepo(session).add(name="Acme", origin="user", resolution="unresolved")
        ).id
        await session.commit()
    url = f"{BASE}/{company}/contacts"
    assert (await env.client.post(url, json={"name": "Jane"})).status_code == 201

    async def blind(self: ContactsRepo, company_id: UUID, key: str) -> None:
        return None  # the duplicate check of a request that ran at the same moment saw nothing

    monkeypatch.setattr(ContactsRepo, "find_by_name_key", blind)
    second = await env.client.post(url, json={"name": "Jane"})

    assert second.status_code == 409
    assert second.json()["code"] == "contact_exists"
