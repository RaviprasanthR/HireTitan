"""Interview tracking endpoints (feature 002e, contracts/rest-api.md)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.interviews import SearchInterviewsApiDeps, create_interviews_router
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)
TODAY = date(2026, 11, 6)


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    deps = SearchInterviewsApiDeps(sessions=sessions)
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_interviews_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions)


async def add_job(env: Env, title: str = "Backend Engineer", *, state: str = "applied") -> UUID:
    async with env.sessions() as session:
        companies = CompaniesRepo(session)
        known = [c for c in await companies.list_all() if c.name == "Acme"]
        company = (
            known[0]
            if known
            else await companies.add(name="Acme", origin="user", resolution="verified")
        )
        job = await JobsRepo(session).add(
            company_id=company.id,
            company_name="Acme",
            title=title,
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="d",
            state=state,
            applied_on=TODAY if state == "applied" else None,
            inquired_on=TODAY if state == "inquired" else None,
        )
        await session.commit()
        return job.id


async def test_read_empty_details(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.get(f"/api/v1/jobs/{job_id}/interview")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": str(job_id),
        "can_edit": True,
        "can_add_round": True,
        "contact": None,
        "source": None,
        "rounds": [],
        "status": {"state": "applied", "round": None},
    }


async def test_read_unknown_job_404(env: Env) -> None:
    response = await env.client.get("/api/v1/jobs/00000000-0000-7000-8000-000000000999/interview")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("state", "editable"),
    [("applied", True), ("inquired", True), ("explore", False), ("skipped", False)],
)
async def test_can_edit_false_outside_the_pipeline(env: Env, state: str, editable: bool) -> None:
    job_id = await add_job(env, state=state)

    body = (await env.client.get(f"/api/v1/jobs/{job_id}/interview")).json()

    assert body["can_edit"] is editable
    assert body["can_add_round"] is editable
    assert body["status"] == {"state": state, "round": None}


# --- contact and source (US1) ----------------------------------------------------------------


def url(job_id: UUID, tail: str = "") -> str:
    return f"/api/v1/jobs/{job_id}/interview{tail}"


async def test_US1_AS2_contact_with_only_a_name(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(url(job_id, "/contact"), json={"name": "Asha Rao"})

    assert response.status_code == 200
    assert response.json()["contact"] == {
        "name": "Asha Rao",
        "role": None,
        "email": None,
        "phone": None,
        "linkedin_url": None,
    }
    assert (await env.client.get(url(job_id))).json()["contact"]["name"] == "Asha Rao"


async def test_US1_contact_keeps_every_field_and_a_second_save_replaces_them(env: Env) -> None:
    job_id = await add_job(env)
    full = {
        "name": "Asha Rao",
        "role": "Recruiter",
        "email": "asha@example.com",
        "phone": "+91 98765 43210",
        "linkedin_url": "linkedin.com/in/asha",
    }
    await env.client.put(url(job_id, "/contact"), json=full)

    response = await env.client.put(url(job_id, "/contact"), json={"name": "Ben"})

    contact = response.json()["contact"]
    assert contact["name"] == "Ben"
    assert contact["role"] is None  # a save replaces every field
    first = await env.client.put(url(job_id, "/contact"), json=full)
    assert first.json()["contact"]["linkedin_url"] == "https://linkedin.com/in/asha"


async def test_US1_AS3_bad_email_refused(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(
        url(job_id, "/contact"), json={"name": "Asha", "email": "not-an-email"}
    )

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["email"]
    assert (await env.client.get(url(job_id))).json()["contact"] is None  # nothing saved


async def test_US1_AS3_bad_linkedin_refused(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(
        url(job_id, "/contact"), json={"name": "Asha", "linkedin_url": "not a link"}
    )

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["linkedin_url"]


async def test_US1_contact_needs_a_name(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(url(job_id, "/contact"), json={"role": "Recruiter"})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["name"]


async def test_US1_clear_the_contact(env: Env) -> None:
    job_id = await add_job(env)
    await env.client.put(url(job_id, "/contact"), json={"name": "Asha"})
    await env.client.put(url(job_id, "/source"), json={"kind": "direct"})

    response = await env.client.delete(url(job_id, "/contact"))

    assert response.status_code == 200
    body = response.json()
    assert body["contact"] is None
    assert body["source"] == {"kind": "direct", "firm_name": None}  # the source stays


async def test_US1_AS4_hiring_firm_needs_a_name(env: Env) -> None:
    job_id = await add_job(env)

    refused = await env.client.put(url(job_id, "/source"), json={"kind": "hiring_firm"})
    saved = await env.client.put(
        url(job_id, "/source"), json={"kind": "hiring_firm", "firm_name": "TalentBridge"}
    )

    assert refused.status_code == 422
    assert [e["field"] for e in refused.json()["errors"]] == ["firm_name"]
    assert saved.json()["source"] == {"kind": "hiring_firm", "firm_name": "TalentBridge"}


async def test_US1_switch_to_direct_clears_the_firm(env: Env) -> None:
    job_id = await add_job(env)
    await env.client.put(
        url(job_id, "/source"), json={"kind": "hiring_firm", "firm_name": "TalentBridge"}
    )

    response = await env.client.put(
        url(job_id, "/source"), json={"kind": "direct", "firm_name": "Ignored"}
    )

    assert response.json()["source"] == {"kind": "direct", "firm_name": None}
    cleared = await env.client.put(url(job_id, "/source"), json={"kind": None})
    assert cleared.json()["source"] is None


async def test_US1_unknown_source_kind_refused(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(url(job_id, "/source"), json={"kind": "agency"})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["kind"]


@pytest.mark.parametrize("state", ["explore", "skipped"])
async def test_R6_not_in_pipeline_refused(env: Env, state: str) -> None:
    job_id = await add_job(env, state=state)

    contact = await env.client.put(url(job_id, "/contact"), json={"name": "Asha"})
    source = await env.client.put(url(job_id, "/source"), json={"kind": "direct"})
    clear = await env.client.delete(url(job_id, "/contact"))

    for response in (contact, source, clear):
        assert response.status_code == 409
        assert response.json()["reason"] == "not_in_pipeline"


async def test_US1_writes_to_an_unknown_job_are_404(env: Env) -> None:
    missing = UUID("00000000-0000-7000-8000-000000000999")

    assert (await env.client.put(url(missing, "/contact"), json={"name": "A"})).status_code == 404
    assert (await env.client.put(url(missing, "/source"), json={"kind": None})).status_code == 404


# --- review fixes -----------------------------------------------------------------------------


async def test_review_a_null_name_is_a_field_error(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(url(job_id, "/contact"), json={"name": None})

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["errors"]] == ["name"]


async def test_review_an_empty_kind_clears_the_source(env: Env) -> None:
    job_id = await add_job(env)
    await env.client.put(url(job_id, "/source"), json={"kind": "direct"})

    response = await env.client.put(url(job_id, "/source"), json={"kind": ""})

    assert response.status_code == 200
    assert response.json()["source"] is None


async def test_review_a_huge_field_is_refused_at_the_boundary(env: Env) -> None:
    job_id = await add_job(env)

    response = await env.client.put(url(job_id, "/contact"), json={"name": "x" * 5000})

    assert response.status_code == 422


async def test_review_saving_contact_and_source_at_once_both_work(env: Env) -> None:
    import asyncio

    job_id = await add_job(env)

    contact, source = await asyncio.gather(
        env.client.put(url(job_id, "/contact"), json={"name": "Asha Rao"}),
        env.client.put(
            url(job_id, "/source"), json={"kind": "hiring_firm", "firm_name": "TalentBridge"}
        ),
    )

    assert (contact.status_code, source.status_code) == (200, 200)
    body = (await env.client.get(url(job_id))).json()
    assert body["contact"]["name"] == "Asha Rao"
    assert body["source"] == {"kind": "hiring_firm", "firm_name": "TalentBridge"}
