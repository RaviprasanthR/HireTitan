"""T063: deleting one resume file (FR-034, US4 scenario 1)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.runtime.domain.run_state import RunStatus, WaitingFor
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.storage.local import LocalFileStorage
from hiretitan.profile.api.resumes import ProfileApiDeps, create_resumes_router
from hiretitan.profile.domain.content import Contact, ProfileContent
from hiretitan.profile.infra.repos import Provenance, ResumeFilesRepo, ReviewsRepo, VersionsRepo

PROVENANCE = Provenance("extract_profile", "1", "fake", "fake-model")


@dataclass
class FakeQueue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: object = None) -> None:
        self.enqueued.append(run_id)


@dataclass
class Env:
    client: httpx.AsyncClient
    storage: LocalFileStorage
    sessions: async_sessionmaker[AsyncSession]


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    storage = LocalFileStorage(tmp_path / "data")
    deps = ProfileApiDeps(sessions=sessions, storage=storage, queue=FakeQueue())
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_resumes_router(deps)]
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield Env(client, storage, sessions)


async def add_file(env: Env, data: bytes = b"resume text one") -> tuple[UUID, str]:
    sha = env.storage.put(data)
    env.storage.put_text(sha, "txt", "extracted")
    async with env.sessions() as session:
        file = await ResumeFilesRepo(session).create(
            kind="pasted_text", original_name="pasted text", size_bytes=len(data), sha256=sha
        )
        await session.commit()
    return file.id, sha


async def add_open_review(env: Env, file_id: UUID, status: RunStatus) -> tuple[UUID, UUID]:
    async with env.sessions() as session:
        runs = RunsRepo(session)
        run = await runs.create("profile_ingest", subject_id=file_id)
        await runs.transition(run.id, RunStatus.running)
        if status is RunStatus.awaiting_review:
            await runs.transition(
                run.id, RunStatus.awaiting_review, waiting_for=WaitingFor.profile_review
            )
        review = await ReviewsRepo(session).create(
            run_id=run.id,
            resume_file_id=file_id,
            extraction={},
            dropped_items=[],
            flags={},
            provenance=PROVENANCE,
        )
        await session.commit()
    return review.id, run.id


async def test_US4_AS1_file_and_pending_review_removed(env: Env) -> None:
    file_id, sha = await add_file(env)
    review_id, run_id = await add_open_review(env, file_id, RunStatus.awaiting_review)

    response = await env.client.delete(f"/api/v1/resumes/{file_id}")

    assert response.status_code == 204
    async with env.sessions() as session:
        assert await ResumeFilesRepo(session).get(file_id) is None
        assert await ReviewsRepo(session).get(review_id) is None
        run = await RunsRepo(session).get(run_id)
    assert run is not None
    assert run.state.status is RunStatus.cancelled
    assert not env.storage.exists(sha)
    with pytest.raises(FileNotFoundError):
        env.storage.get_text(sha, "txt")


async def test_US4_AS1_versions_keep_content_show_source_deleted(env: Env) -> None:
    file_id, _ = await add_file(env)
    async with env.sessions() as session:
        version = await VersionsRepo(session).create_version(
            ProfileContent(contact=Contact(name="Jane"), skills=("Go",)),
            created_by="extraction",
            source_file_id=file_id,
            provenance=PROVENANCE,
        )
        await session.commit()

    response = await env.client.delete(f"/api/v1/resumes/{file_id}")

    assert response.status_code == 204
    async with env.sessions() as session:
        kept = await VersionsRepo(session).get(version.id)
    assert kept is not None
    assert kept.source_deleted is True
    assert kept.source_file_id is None
    assert kept.content.skills == ("Go",)
    assert kept.provenance == PROVENANCE


async def test_shared_hash_file_kept_while_referenced(env: Env) -> None:
    first, sha = await add_file(env)
    second, same_sha = await add_file(env)
    assert sha == same_sha

    assert (await env.client.delete(f"/api/v1/resumes/{first}")).status_code == 204
    assert env.storage.exists(sha)

    assert (await env.client.delete(f"/api/v1/resumes/{second}")).status_code == 204
    assert not env.storage.exists(sha)


async def test_unknown_file_is_404(env: Env) -> None:
    response = await env.client.delete(f"/api/v1/resumes/{uuid4()}")
    assert response.status_code == 404


async def test_file_being_read_right_now_is_409_and_kept(env: Env) -> None:
    file_id, sha = await add_file(env)
    await add_open_review(env, file_id, RunStatus.running)

    response = await env.client.delete(f"/api/v1/resumes/{file_id}")

    assert response.status_code == 409
    async with env.sessions() as session:
        assert await ResumeFilesRepo(session).get(file_id) is not None
    assert env.storage.exists(sha)
