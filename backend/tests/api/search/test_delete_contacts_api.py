"""T027: contacts and notes through the delete paths, end to end over HTTP (US4; FR-023, FR-025)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.storage.local import LocalFileStorage
from hiretitan.search.api.companies import SearchCompaniesApiDeps, create_companies_router
from hiretitan.search.api.contacts import SearchContactsApiDeps, create_contacts_router
from hiretitan.search.application.seed import load_seed
from hiretitan.search.infra.careerops.fake import FileCareerOps
from hiretitan.search.infra.repos import CompaniesRepo
from hiretitan.setup.api.data import DataApiDeps, create_data_router
from hiretitan.setup_wiring import SqlDeleteAllStore

NOW = datetime(2026, 11, 11, 9, tzinfo=UTC)
FIXTURES = Path(__file__).parents[2] / "fixtures" / "companies"
COMPANIES = "/api/v1/companies"


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(
    sessions: async_sessionmaker[AsyncSession],
    profile_saver: BaseCheckpointSaver,  # type: ignore[type-arg]  # creates the lg tables
    tmp_path: Path,
) -> AsyncIterator[Env]:
    async def enqueue_key_check() -> None:
        return None

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
            create_data_router(
                DataApiDeps(
                    sessions=sessions,
                    storage=LocalFileStorage(tmp_path / "data"),
                    store=partial(SqlDeleteAllStore, company_seed=FIXTURES / "seed_v1.yaml"),
                    enqueue_key_check=enqueue_key_check,
                )
            ),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions)


async def seeded(env: Env) -> UUID:
    """A shipped company, as the install has after the first start."""
    async with env.sessions() as session:
        await load_seed(CompaniesRepo(session), FIXTURES / "seed_v1.yaml")
        await session.commit()
        row = await CompaniesRepo(session).get_by_key("example-alpha")
        assert row is not None
        return row.id


async def own_company(env: Env, name: str = "My Own Co") -> UUID:
    response = await env.client.post(
        COMPANIES, json={"name": name, "careers_url": "https://own.example.test/careers"}
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def fill(env: Env, company: UUID) -> None:
    contact = await env.client.post(
        f"{COMPANIES}/{company}/contacts", json={"name": "Jane Example", "role": "Recruiter"}
    )
    assert contact.status_code == 201, contact.text
    note = await env.client.put(f"{COMPANIES}/{company}/note", json={"body": "Private note."})
    assert note.status_code == 200, note.text


async def rows(env: Env, table: str) -> int:
    async with env.sessions() as session:
        return int((await session.execute(text(f"SELECT count(*) FROM app.{table}"))).scalar_one())


async def test_US4_AS1_delete_all_removes_contacts_and_notes_via_api(env: Env) -> None:
    await fill(env, await own_company(env))
    await fill(env, await seeded(env))
    assert (await rows(env, "company_contacts"), await rows(env, "company_notes")) == (2, 2)

    response = await env.client.post("/api/v1/data/delete-all", json={"confirm": "DELETE"})

    assert response.status_code == 204
    assert await rows(env, "company_contacts") == 0
    assert await rows(env, "company_notes") == 0
    listed = (await env.client.get(COMPANIES)).json()
    assert all(c["contact_count"] == 0 and c["has_note"] is False for c in listed["items"])


async def test_FR023_deleting_own_company_removes_its_contacts_via_api(env: Env) -> None:
    mine = await own_company(env)
    other = await own_company(env, "Other Own Co")
    await fill(env, mine)
    await fill(env, other)

    response = await env.client.delete(f"{COMPANIES}/{mine}")

    assert response.status_code == 204
    assert await rows(env, "company_contacts") == 1  # only the other company's contact is left
    assert await rows(env, "company_notes") == 1
    left = (await env.client.get(f"{COMPANIES}/{other}/contacts")).json()
    assert [c["name"] for c in left["items"]] == ["Jane Example"]
    assert left["note"]["body"] == "Private note."


async def test_hidden_company_keeps_contacts(env: Env) -> None:
    company = await own_company(env)
    await fill(env, company)

    hidden = await env.client.patch(f"{COMPANIES}/{company}", json={"hidden": True})
    assert hidden.status_code == 200

    panel = (await env.client.get(f"{COMPANIES}/{company}/contacts")).json()
    assert [c["name"] for c in panel["items"]] == ["Jane Example"]
    assert panel["note"]["body"] == "Private note."
    assert await rows(env, "company_contacts") == 1


async def test_FR025_contacts_survive_a_shipped_list_update(env: Env) -> None:
    company = await seeded(env)
    await fill(env, company)

    async with env.sessions() as session:
        await load_seed(CompaniesRepo(session), FIXTURES / "seed_v2.yaml")
        await session.commit()

    panel = (await env.client.get(f"{COMPANIES}/{company}/contacts")).json()
    assert [c["name"] for c in panel["items"]] == ["Jane Example"]
    assert panel["note"]["body"] == "Private note."
