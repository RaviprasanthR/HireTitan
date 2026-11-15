"""The resume a person used: marking jobs, undo and the pipeline resumes endpoint (feature 002f)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.interviews import SearchInterviewsApiDeps, create_interviews_router
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.api.pipeline import PipelineApiDeps, create_pipeline_router
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo
from hiretitan.search_wiring import SqlResumeLookup

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)
TODAY = date(2026, 11, 6)


class _Queue:
    async def enqueue(self, run_id: UUID, resume: object = None) -> None:
        raise AssertionError("marking never starts a run")


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    deps = SearchJobsApiDeps(
        sessions=sessions, queue=_Queue(), clock=FakeClock(NOW), resume_lookup=SqlResumeLookup
    )
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_search_jobs_router(deps),
            create_pipeline_router(PipelineApiDeps(sessions)),
            create_interviews_router(SearchInterviewsApiDeps(sessions=sessions)),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions)


async def add_job(env: Env, title: str = "Backend Engineer") -> UUID:
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
            state="explore",
        )
        await session.commit()
        return job.id


async def add_file(env: Env, name: str, status: str = "parsed") -> UUID:
    async with env.sessions() as session:
        file_id = (
            await session.execute(
                text(
                    "INSERT INTO app.resume_files (id, kind, original_name, size_bytes, sha256, "
                    "parse_status, created_at) VALUES (gen_random_uuid(), 'upload_pdf', :name, "
                    "1000, :sha, :status, '2025-03-14T09:00:00+00:00') RETURNING id"
                ),
                {"name": name, "sha": "a" * 64, "status": status},
            )
        ).scalar_one()
        await session.commit()
        return file_id


async def stored(env: Env, job_id: UUID) -> tuple[UUID | None, str | None]:
    async with env.sessions() as session:
        row = (await InterviewsRepo(session).details(job_id)).details
    return (None, None) if row is None else (row.resume_file_id, row.resume_name)


async def last_choice(env: Env) -> UUID | None:
    body = (await env.client.get("/api/v1/pipeline/resumes")).json()
    return UUID(body["last_choice"]) if body["last_choice"] else None


async def test_FR001_mark_applied_records_the_chosen_resume(env: Env) -> None:
    job_id = await add_job(env)
    file_id = await add_file(env, "Backend_2025.pdf")

    marked = await env.client.post(
        f"/api/v1/jobs/{job_id}/applied", json={"resume_file_id": str(file_id)}
    )

    assert marked.status_code == 200
    assert marked.json()["state"] == "applied"
    assert await stored(env, job_id) == (file_id, "Backend_2025.pdf")
    assert await last_choice(env) == file_id


async def test_FR001_mark_inquired_records_the_chosen_resume(env: Env) -> None:
    job_id = await add_job(env)
    file_id = await add_file(env, "Backend_2025.pdf")

    marked = await env.client.post(
        f"/api/v1/jobs/{job_id}/inquired", json={"resume_file_id": str(file_id)}
    )

    assert marked.status_code == 200
    assert await stored(env, job_id) == (file_id, "Backend_2025.pdf")


async def test_FR002_mark_without_resume_field_behaves_as_before(env: Env) -> None:
    job_id = await add_job(env)

    for body in (None, {}, {"applied_on": "2026-11-03"}):
        marked = await env.client.post(f"/api/v1/jobs/{job_id}/applied", json=body)
        assert marked.status_code == 200
        await env.client.delete(f"/api/v1/jobs/{job_id}/applied")

    assert await stored(env, job_id) == (None, None)
    assert await last_choice(env) is None


async def test_FR003_inquired_to_applied_keeps_the_resume(env: Env) -> None:
    job_id = await add_job(env)
    mine = await add_file(env, "Mine.pdf")
    other = await add_file(env, "Other.pdf")
    await env.client.post(f"/api/v1/jobs/{job_id}/inquired", json={"resume_file_id": str(mine)})
    await env.client.post(f"/api/v1/jobs/{job_id}/inquired", json={})  # already inquired: 409
    # another job's mark moves the last choice elsewhere
    await env.client.post(
        f"/api/v1/jobs/{await add_job(env, 'Other job')}/applied",
        json={"resume_file_id": str(other)},
    )

    applied = await env.client.post(f"/api/v1/jobs/{job_id}/applied", json={})

    assert applied.status_code == 200
    assert await stored(env, job_id) == (mine, "Mine.pdf")
    assert await last_choice(env) == other  # an absent field does not touch the last choice


async def test_FR001_mark_with_null_records_none_and_remembers_none(env: Env) -> None:
    first = await add_job(env, "First")
    second = await add_job(env, "Second")
    file_id = await add_file(env, "Backend_2025.pdf")
    await env.client.post(f"/api/v1/jobs/{first}/applied", json={"resume_file_id": str(file_id)})
    assert await last_choice(env) == file_id

    marked = await env.client.post(f"/api/v1/jobs/{second}/applied", json={"resume_file_id": None})

    assert marked.status_code == 200
    assert await stored(env, second) == (None, None)
    assert await last_choice(env) is None


async def test_FR008_undo_clears_the_resume(env: Env) -> None:
    job_id = await add_job(env)
    file_id = await add_file(env, "Backend_2025.pdf")
    await env.client.post(f"/api/v1/jobs/{job_id}/applied", json={"resume_file_id": str(file_id)})

    undone = await env.client.delete(f"/api/v1/jobs/{job_id}/applied")

    assert undone.status_code == 200
    assert undone.json()["state"] == "explore"
    assert await stored(env, job_id) == (None, None)
    assert await last_choice(env) == file_id  # undo does not change the starting value


async def test_FR008_undo_inquired_clears_the_resume(env: Env) -> None:
    job_id = await add_job(env)
    file_id = await add_file(env, "Backend_2025.pdf")
    await env.client.post(f"/api/v1/jobs/{job_id}/inquired", json={"resume_file_id": str(file_id)})

    undone = await env.client.delete(f"/api/v1/jobs/{job_id}/inquired")

    assert undone.status_code == 200
    assert await stored(env, job_id) == (None, None)


@pytest.mark.parametrize("kind", ["not_resume_file", "unknown_file"])
async def test_FR012_not_a_resume_file_is_refused(env: Env, kind: str) -> None:
    job_id = await add_job(env)
    earlier = await add_file(env, "Earlier.pdf")
    await env.client.post(
        f"/api/v1/jobs/{await add_job(env, 'Seed job')}/applied",
        json={"resume_file_id": str(earlier)},
    )
    bad = (
        await add_file(env, "Letter.pdf", "not_resume")
        if kind == "not_resume_file"
        else UUID("00000000-0000-4000-8000-000000000001")
    )

    marked = await env.client.post(
        f"/api/v1/jobs/{job_id}/applied", json={"resume_file_id": str(bad)}
    )

    assert marked.status_code == 422
    assert [e["field"] for e in marked.json()["errors"]] == ["resume_file_id"]
    # nothing changed: the job is still in Explore, and the last choice is what it was
    async with env.sessions() as session:
        row = await JobsRepo(session).get(job_id)
        assert row is not None
        assert row.state == "explore"
    assert await stored(env, job_id) == (None, None)
    assert await last_choice(env) == earlier


async def test_pipeline_resumes_last_choice_and_usage(env: Env) -> None:
    empty = (await env.client.get("/api/v1/pipeline/resumes")).json()
    assert empty == {"last_choice": None, "usage": []}
    first = await add_file(env, "A.pdf")
    second = await add_file(env, "B.pdf")
    for title, file_id in (("One", first), ("Two", first), ("Three", second)):
        await env.client.post(
            f"/api/v1/jobs/{await add_job(env, title)}/applied",
            json={"resume_file_id": str(file_id)},
        )

    body = (await env.client.get("/api/v1/pipeline/resumes")).json()

    assert body["last_choice"] == str(second)
    assert {u["resume_file_id"]: u["jobs"] for u in body["usage"]} == {
        str(first): 2,
        str(second): 1,
    }


async def test_a_file_being_chosen_cannot_be_removed_until_the_mark_ends(env: Env) -> None:
    """The lookup holds the file row, so a removal in the middle of a mark waits instead of
    leaving the mark to fail on a link to a file that is gone (review finding, T007r)."""
    file_id = await add_file(env, "Backend_2025.pdf")
    async with env.sessions() as marking:
        facts = await SqlResumeLookup(marking).get(file_id)
        assert facts is not None
        async with env.sessions() as removing:
            await removing.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(DBAPIError):  # waits for the mark, then gives up
                await removing.execute(
                    text("DELETE FROM app.resume_files WHERE id = :id"), {"id": file_id}
                )
        await marking.rollback()


# --- the resume on cards and details (US2) ---------------------------------------------------

CHOSEN = {"state": "chosen", "name": "Backend_2025.pdf", "added_on": "2025-03-14"}
NONE = {"state": "none", "resume_file_id": None, "name": None, "added_on": None}


async def pipeline_cards(env: Env) -> dict[str, dict]:
    items = (await env.client.get("/api/v1/jobs?list=pipeline")).json()["items"]
    return {card["title"]: card for card in items}


async def test_FR004_pipeline_cards_carry_the_resume(env: Env) -> None:
    with_resume = await add_job(env, "With resume")
    without = await add_job(env, "Without resume")
    file_id = await add_file(env, "Backend_2025.pdf")
    await env.client.post(
        f"/api/v1/jobs/{with_resume}/applied", json={"resume_file_id": str(file_id)}
    )
    await env.client.post(f"/api/v1/jobs/{without}/applied")

    cards = await pipeline_cards(env)

    assert cards["With resume"]["resume"] == {**CHOSEN, "resume_file_id": str(file_id)}
    assert cards["Without resume"]["resume"] == NONE


async def test_FR005_interview_details_and_job_detail_carry_the_resume(env: Env) -> None:
    job_id = await add_job(env)
    file_id = await add_file(env, "Backend_2025.pdf")
    marked = await env.client.post(
        f"/api/v1/jobs/{job_id}/applied", json={"resume_file_id": str(file_id)}
    )
    expected = {**CHOSEN, "resume_file_id": str(file_id)}

    interview = await env.client.get(f"/api/v1/jobs/{job_id}/interview")
    detail = await env.client.get(f"/api/v1/jobs/{job_id}")

    assert marked.json()["resume"] == expected  # the mark's own response already shows it
    assert interview.json()["resume"] == expected
    assert detail.json()["resume"] == expected


async def test_FR006_jobs_before_the_feature_have_none(env: Env) -> None:
    explore = await add_job(env, "Still in Explore")
    applied = await add_job(env, "Applied as before")
    await env.client.post(f"/api/v1/jobs/{applied}/applied", json={})

    assert (await env.client.get(f"/api/v1/jobs/{explore}")).json()["resume"] == NONE
    assert (await pipeline_cards(env))["Applied as before"]["resume"] == NONE
    assert (await env.client.get(f"/api/v1/jobs/{applied}/interview")).json()["resume"] == NONE


async def test_FR009_a_removed_file_shows_as_a_removed_note(env: Env) -> None:
    job_id = await add_job(env)
    file_id = await add_file(env, "Backend_2025.pdf")
    await env.client.post(f"/api/v1/jobs/{job_id}/applied", json={"resume_file_id": str(file_id)})

    async with env.sessions() as session:
        await session.execute(text("DELETE FROM app.resume_files WHERE id = :id"), {"id": file_id})
        await session.commit()

    note = {
        "state": "removed",
        "resume_file_id": None,
        "name": "Backend_2025.pdf",
        "added_on": "2025-03-14",
    }
    assert (await pipeline_cards(env))["Backend Engineer"]["resume"] == note
    assert (await env.client.get(f"/api/v1/jobs/{job_id}/interview")).json()["resume"] == note
