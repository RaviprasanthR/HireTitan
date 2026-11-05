"""T045: review endpoints (draft, confirm, discard) and the run endpoints."""

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
from hiretitan.platform.runtime.api import create_runs_router
from hiretitan.platform.runtime.domain.run_state import RunStatus, WaitingFor
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.profile.api.resumes import ProfileApiDeps
from hiretitan.profile.api.reviews import create_reviews_router
from hiretitan.profile.infra.repos import ReviewsRepo, VersionsRepo

PDF = "synthetic-mid-2page.pdf"


@dataclass
class FakeQueue:
    jobs: list[tuple[UUID, Any]] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.jobs.append((run_id, resume))


@dataclass
class Env:
    client: httpx.AsyncClient
    queue: FakeQueue
    h: Harness


@pytest.fixture
async def env(
    make_harness: Callable[..., Harness],
    sessions: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> AsyncIterator[Env]:
    h = make_harness([jane_extraction()])
    queue = FakeQueue()
    deps = ProfileApiDeps(sessions=sessions, storage=h.storage, queue=queue)
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[create_reviews_router(deps), create_runs_router(sessions, queue)],
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield Env(client, queue, h)


async def reviewed(env: Env) -> tuple[UUID, UUID]:
    """Run the workflow to the review pause; return (review id, run id)."""
    run_id = await env.h.start(PDF)
    await env.h.run(run_id)
    review = await env.h.review()
    assert review is not None
    return review.id, run_id


async def get_review(env: Env, review_id: UUID) -> dict[str, Any]:
    response = await env.client.get(f"/api/v1/profile/reviews/{review_id}")
    assert response.status_code == 200
    return response.json()  # type: ignore[no-any-return]


async def test_review_detail_has_everything_the_editor_needs(env: Env) -> None:
    review_id, run_id = await reviewed(env)
    body = await get_review(env, review_id)

    assert body["id"] == str(review_id)
    assert body["run_id"] == str(run_id)
    assert body["status"] == "open"
    assert body["extraction"]["contact"]["name"] == "Jane Example"
    assert body["draft"] is None
    assert body["dropped_items"] == []
    assert set(body["flags"]) >= {"hidden_text", "injection_flags", "truncated_at"}
    assert body["compare_to"] is None
    assert body["changed_paths"] == []
    assert body["provenance"] == {
        "prompt_name": "extract_profile",
        "prompt_version": "2",
        "provider": "fake",
        "model": "fake-model",
    }


async def test_unknown_review_is_404(env: Env) -> None:
    response = await env.client.get(f"/api/v1/profile/reviews/{UUID(int=1)}")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_US1_AS9_draft_kept_until_confirm_or_discard(env: Env) -> None:
    review_id, _ = await reviewed(env)
    draft = (await get_review(env, review_id))["extraction"]
    draft["headline"] = "Work in progress"
    draft["contact"]["name"] = ""  # incomplete drafts are allowed (FR-016)

    saved = await env.client.put(f"/api/v1/profile/reviews/{review_id}/draft", json=draft)

    assert saved.status_code == 200
    assert saved.json()["draft_saved_at"]
    again = await get_review(env, review_id)
    assert again["draft"]["headline"] == "Work in progress"
    assert again["draft"]["contact"]["name"] == ""
    assert again["extraction"]["headline"] is None  # the AI's version is kept as it was
    assert again["status"] == "open"


async def test_draft_with_oversized_field_is_422_with_the_field_name(env: Env) -> None:
    review_id, _ = await reviewed(env)
    draft = (await get_review(env, review_id))["extraction"]
    draft["headline"] = "x" * 201
    response = await env.client.put(f"/api/v1/profile/reviews/{review_id}/draft", json=draft)
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "headline"


async def test_FR018_confirm_blocked_with_reasons(env: Env) -> None:
    review_id, run_id = await reviewed(env)
    content = (await get_review(env, review_id))["extraction"]
    content["contact"]["name"] = " "
    content["experience"][0]["end"] = {"year": 2019, "month": None}  # before its 2021 start
    content["experience"][0]["current"] = False

    response = await env.client.post(f"/api/v1/profile/reviews/{review_id}/confirm", json=content)

    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert fields == {"contact.name", "experience[0].end"}
    assert env.queue.jobs == []  # nothing was resumed
    assert (await env.h.state(run_id)).waiting_for is WaitingFor.profile_review


async def test_US1_AS2_confirm_saves_exact_values_linked_to_file(env: Env) -> None:
    review_id, run_id = await reviewed(env)
    content = (await get_review(env, review_id))["extraction"]
    content["headline"] = "Exactly this headline"
    content["skills"] = ["Python", "My own skill"]  # edits are the user's own words: no grounding

    response = await env.client.post(f"/api/v1/profile/reviews/{review_id}/confirm", json=content)

    assert response.status_code == 202
    assert response.json() == {"run_id": str(run_id)}
    [(queued_run, resume)] = env.queue.jobs
    assert queued_run == run_id
    assert resume["action"] == "confirm"
    assert (await env.h.state(run_id)).status is RunStatus.queued

    await env.h.run(run_id, resume=resume)  # what the worker does next

    async with env.h.sessions() as session:
        version = await VersionsRepo(session).current()
    assert version is not None
    assert version.content.headline == "Exactly this headline"
    assert version.content.skills == ("Python", "My own skill")
    assert version.created_by == "extraction"
    file = await env.h.file_for(run_id)
    assert version.source_file_id == file.id


async def test_confirm_twice_is_a_conflict(env: Env) -> None:
    review_id, _ = await reviewed(env)
    content = (await get_review(env, review_id))["extraction"]
    first = await env.client.post(f"/api/v1/profile/reviews/{review_id}/confirm", json=content)
    second = await env.client.post(f"/api/v1/profile/reviews/{review_id}/confirm", json=content)
    assert first.status_code == 202
    assert second.status_code == 409


async def test_FR014_discard_leaves_current_unchanged(env: Env) -> None:
    from hiretitan.profile.domain.content import Contact, ProfileContent

    async with env.h.sessions() as session:
        current = await VersionsRepo(session).create_version(
            ProfileContent(contact=Contact(name="Existing"), skills=("Go",)), created_by="manual"
        )
        await session.commit()
    review_id, run_id = await reviewed(env)

    response = await env.client.post(f"/api/v1/profile/reviews/{review_id}/discard")

    assert response.status_code == 204
    async with env.h.sessions() as session:
        review = await ReviewsRepo(session).get(review_id)
        still = await VersionsRepo(session).current()
    assert review is not None
    assert review.status == "discarded"
    assert still is not None
    assert still.id == current.id
    assert (await env.h.state(run_id)).status is RunStatus.cancelled
    assert await env.h.review() is None  # a new upload is possible again


async def test_discarding_twice_is_a_conflict(env: Env) -> None:
    review_id, _ = await reviewed(env)
    assert (
        await env.client.post(f"/api/v1/profile/reviews/{review_id}/discard")
    ).status_code == 204
    assert (
        await env.client.post(f"/api/v1/profile/reviews/{review_id}/discard")
    ).status_code == 409


async def test_review_detail_includes_the_version_it_is_compared_to(env: Env) -> None:
    from hiretitan.profile.domain.content import Contact, ProfileContent

    async with env.h.sessions() as session:
        await VersionsRepo(session).create_version(
            ProfileContent(contact=Contact(name="Old Jane"), skills=("COBOL",)), created_by="manual"
        )
        await session.commit()
    review_id, _ = await reviewed(env)
    body = await get_review(env, review_id)
    assert body["compare_to"]["contact"]["name"] == "Old Jane"
    assert "skills" in body["changed_paths"]


# ---- run endpoints -------------------------------------------------------------------------
async def test_get_run_shows_status_and_step(env: Env) -> None:
    _, run_id = await reviewed(env)
    response = await env.client.get(f"/api/v1/runs/{run_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(run_id)
    assert (body["workflow"], body["status"]) == ("profile_ingest", "awaiting_review")
    assert body["waiting_for"] == "profile_review"
    assert body["pause_reason"] is None
    assert body["current_step"] == "ready_for_review"
    assert {"error", "updated_at"} <= set(body)


async def test_FR007_decision_manual_entry_opens_empty_review(env: Env) -> None:
    run_id = await env.h.start("attack-ignore-instructions.pdf")
    await env.h.run(run_id)
    assert (await env.h.state(run_id)).waiting_for is WaitingFor.injection_decision

    response = await env.client.post(
        f"/api/v1/runs/{run_id}/decision", json={"decision": "manual_entry"}
    )

    assert response.status_code == 202
    [(queued, resume)] = env.queue.jobs
    assert (queued, resume) == (run_id, {"decision": "manual_entry"})
    await env.h.run(run_id, resume=resume)
    review = await env.h.review()
    assert review is not None
    assert review.extraction["experience"] == []


async def test_decision_must_be_one_of_the_two_choices(env: Env) -> None:
    run_id = await env.h.start("attack-ignore-instructions.pdf")
    await env.h.run(run_id)
    response = await env.client.post(f"/api/v1/runs/{run_id}/decision", json={"decision": "nope"})
    assert response.status_code == 422


async def test_decision_only_when_waiting_for_one(env: Env) -> None:
    _, run_id = await reviewed(env)  # waiting for profile_review, not a decision
    response = await env.client.post(
        f"/api/v1/runs/{run_id}/decision", json={"decision": "continue_extraction"}
    )
    assert response.status_code == 409


async def test_retry_failed_run(env: Env) -> None:
    run_id = await env.h.start(PDF)
    async with env.h.sessions() as session:
        runs = RunsRepo(session)
        await runs.transition(run_id, RunStatus.running)
        await runs.transition(run_id, RunStatus.failed, error="Something went wrong")
        await session.commit()

    response = await env.client.post(f"/api/v1/runs/{run_id}/retry")

    assert response.status_code == 202
    assert env.queue.jobs == [(run_id, None)]
    assert (await env.h.state(run_id)).status is RunStatus.queued


async def test_retry_that_cannot_be_queued_leaves_the_run_failed(env: Env) -> None:
    run_id = await env.h.start(PDF)
    async with env.h.sessions() as session:
        runs = RunsRepo(session)
        await runs.transition(run_id, RunStatus.running)
        await runs.transition(run_id, RunStatus.failed, error="Something went wrong")
        await session.commit()

    async def broken(run_id: UUID, resume: Any = None) -> None:
        raise ConnectionError("queue is down")

    env.queue.enqueue = broken  # type: ignore[method-assign]
    with pytest.raises(ConnectionError):
        await env.client.post(f"/api/v1/runs/{run_id}/retry")

    state = await env.h.state(run_id)
    assert state.status is RunStatus.failed  # not stuck as queued with no job

    env.queue.enqueue = FakeQueue().enqueue  # type: ignore[method-assign]
    assert (await env.client.post(f"/api/v1/runs/{run_id}/retry")).status_code == 202


async def test_retry_only_for_failed_runs(env: Env) -> None:
    _, run_id = await reviewed(env)
    assert (await env.client.post(f"/api/v1/runs/{run_id}/retry")).status_code == 409


async def test_unknown_run_is_404(env: Env) -> None:
    assert (await env.client.get(f"/api/v1/runs/{UUID(int=5)}")).status_code == 404
