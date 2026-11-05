"""T046: the confirmed profile and its versions (FR-019 to FR-022)."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workflow" / "profile"))
from harness import Harness, jane_extraction

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings
from hiretitan.profile.api.profile import create_profile_router
from hiretitan.profile.api.resumes import ProfileApiDeps
from hiretitan.profile.application.versions import get_current_profile
from hiretitan.profile.infra.repos import ResumeFilesRepo, VersionsRepo


@dataclass
class FakeQueue:
    jobs: list[Any] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.jobs.append((run_id, resume))


@dataclass
class Env:
    client: httpx.AsyncClient
    h: Harness


@pytest.fixture
async def env(
    make_harness: Callable[..., Harness],
    sessions: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> AsyncIterator[Env]:
    h = make_harness([jane_extraction()])
    deps = ProfileApiDeps(sessions=sessions, storage=h.storage, queue=FakeQueue())
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_profile_router(deps)]
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield Env(client, h)


def content(name: str = "Jane Example", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "contact": {"name": name},
        "experience": [
            {
                "employer": "Acme",
                "title": "Engineer",
                "start": {"year": 2021, "month": 1},
                "current": True,
                "bullets": ["Built things"],
            }
        ],
        "skills": ["Python"],
    }
    base.update(kw)
    return base


async def test_FR022_open_review_not_visible_as_profile(env: Env) -> None:
    run_id = await env.h.start("synthetic-mid-2page.pdf")
    await env.h.run(run_id)
    assert await env.h.review() is not None  # an open review exists

    body = (await env.client.get("/api/v1/profile")).json()
    assert body == {"current": None}
    assert (await env.client.get("/api/v1/profile/versions")).json() == []
    async with env.h.sessions() as session:
        assert await get_current_profile(VersionsRepo(session)) is None


async def test_FR019_manual_profile_without_resume_or_ai(env: Env) -> None:
    response = await env.client.post("/api/v1/profile/versions", json=content())

    assert response.status_code == 201
    created = response.json()
    assert created["number"] == 1
    assert created["created_by"] == "manual"
    assert created["source_file_name"] is None
    assert created["is_current"] is True
    assert env.h.llm.calls == []  # no AI involved

    profile = (await env.client.get("/api/v1/profile")).json()
    assert profile["current"]["id"] == created["id"]
    assert profile["current"]["content"]["contact"]["name"] == "Jane Example"
    async with env.h.sessions() as session:
        loaded = await get_current_profile(VersionsRepo(session))
    assert loaded is not None
    assert loaded.contact.name == "Jane Example"


async def test_FR020_edit_creates_new_version_keeps_old(env: Env) -> None:
    first = (await env.client.post("/api/v1/profile/versions", json=content())).json()
    edited = content(skills=["Python", "Go"])
    second_response = await env.client.post("/api/v1/profile/versions", json=edited)

    assert second_response.status_code == 201
    second = second_response.json()
    assert (second["number"], second["created_by"]) == (2, "manual_edit")

    old = (await env.client.get(f"/api/v1/profile/versions/{first['id']}")).json()
    assert old["content"]["skills"] == ["Python"]  # the old version is untouched
    new = (await env.client.get(f"/api/v1/profile/versions/{second['id']}")).json()
    assert new["content"]["skills"] == ["Python", "Go"]
    assert (await env.client.get("/api/v1/profile")).json()["current"]["id"] == second["id"]


async def test_manual_versions_are_not_grounded(env: Env) -> None:
    # There is no source text to check against: the user's own words are the source.
    response = await env.client.post(
        "/api/v1/profile/versions", json=content(skills=["Anything I Say"])
    )
    assert response.status_code == 201
    assert response.json()["number"] == 1


async def test_FR018_rules_apply_to_manual_versions(env: Env) -> None:
    response = await env.client.post("/api/v1/profile/versions", json=content(name=""))
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "contact.name"
    assert (await env.client.get("/api/v1/profile")).json() == {"current": None}


async def test_FR021_versions_listed_with_source(env: Env) -> None:
    run_id = await env.h.start("synthetic-mid-2page.pdf")
    await env.h.run(run_id)
    review = await env.h.review()
    assert review is not None
    await env.h.resume(run_id, {"action": "confirm", "content": review.extraction})
    await env.client.post("/api/v1/profile/versions", json=content("Jane B"))

    listed = (await env.client.get("/api/v1/profile/versions")).json()

    assert [v["number"] for v in listed] == [2, 1]  # newest first
    assert [v["is_current"] for v in listed] == [True, False]
    assert listed[1]["created_by"] == "extraction"
    assert listed[1]["source_file_name"] == "synthetic-mid-2page.pdf"
    assert listed[1]["source_deleted"] is False
    assert listed[0]["source_file_name"] is None
    assert {"id", "created_at"} <= set(listed[0])

    file = await env.h.file_for(run_id)
    async with env.h.sessions() as session:
        await ResumeFilesRepo(session).delete(file.id)
        await session.commit()
    after = (await env.client.get("/api/v1/profile/versions")).json()
    assert after[1]["source_file_name"] is None
    assert after[1]["source_deleted"] is True
    detail = (await env.client.get(f"/api/v1/profile/versions/{after[1]['id']}")).json()
    assert detail["content"]["contact"]["name"] == "Jane Example"  # content survives


async def test_unknown_version_is_404(env: Env) -> None:
    response = await env.client.get(f"/api/v1/profile/versions/{UUID(int=3)}")
    assert response.status_code == 404
