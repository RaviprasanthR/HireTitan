"""Fixes from the Phase 3-6 reviews (python/FastAPI, security, database) of feature 002b."""

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
from hiretitan.search.api.contacts import SearchContactsApiDeps, create_contacts_router
from hiretitan.search.infra.careerops.fake import FileCareerOps
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo

NOW = datetime(2026, 11, 11, 9, tzinfo=UTC)
BASE = "/api/v1/companies"


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
