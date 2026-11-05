"""T073: "Type it in myself" as an autosaved review (FR-019, US5-AS6)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from hiretitan.platform.runtime.domain.run_state import RunStatus, WaitingFor
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.profile.application.ingest import OpenReviewError
from hiretitan.profile.application.manual import (
    ActiveRunError,
    ReadingInProgressError,
    start_manual_review,
)
from hiretitan.profile.domain.content import Contact, Experience, ProfileContent, YearMonth
from hiretitan.profile.domain.serialization import content_to_json
from hiretitan.profile.infra.ingest_store import SqlIngestStore
from hiretitan.profile.infra.repos import ReviewsRepo, VersionsRepo

sys.path.insert(0, str(Path(__file__).parent))
from harness import Harness

PDF = "synthetic-mid-2page.pdf"


class _Queue:
    def __init__(self) -> None:
        self.jobs: list[UUID] = []

    async def enqueue(self, run_id: UUID, resume: object = None) -> None:
        self.jobs.append(run_id)


async def start_manual(h: Harness, *, cancel: bool = False) -> tuple[UUID, _Queue]:
    queue = _Queue()
    async with h.sessions() as session:
        run_id = await start_manual_review(SqlIngestStore(session), queue, cancel_active_run=cancel)
    return run_id, queue


def typed(name: str = "Jane Example") -> ProfileContent:
    job = Experience(employer="Acme", title="Engineer", start=YearMonth(2021, 1), current=True)
    return ProfileContent(contact=Contact(name=name), experience=(job,), skills=("Python",))


async def test_US5_AS6_manual_review_autosaves_and_confirms(make_harness: Any) -> None:
    h = make_harness([])
    run_id, queue = await start_manual(h)
    assert queue.jobs == [run_id]

    state = await h.run(run_id)

    assert state.status is RunStatus.awaiting_review
    assert state.waiting_for is WaitingFor.profile_review
    review = await h.review()
    assert review is not None
    assert review.resume_file_id is None  # no file
    assert review.extraction["contact"]["name"] == ""  # an empty profile to type into
    assert review.flags["extraction_outcome"] == "manual"
    assert len(h.llm.calls) == 0  # no AI

    async with h.sessions() as session:  # autosave, as the editor does
        await ReviewsRepo(session).set_draft(review.id, typed("Jane"))
        await session.commit()
    again = await h.review()
    assert again is not None
    assert again.draft is not None
    assert again.draft.contact.name == "Jane"

    await h.resume(run_id, {"action": "confirm", "content": content_to_json(typed("Jane"))})

    assert (await h.state(run_id)).status is RunStatus.done
    async with h.sessions() as session:
        version = await VersionsRepo(session).current()
    assert version is not None
    assert version.content.contact.name == "Jane"
    assert version.created_by == "manual"
    assert version.source_file_id is None
    assert version.review_id == review.id


async def test_FR019_manual_version_has_no_provenance(make_harness: Any) -> None:
    h = make_harness([])
    run_id, _ = await start_manual(h)
    await h.run(run_id)
    await h.resume(run_id, {"action": "confirm", "content": content_to_json(typed())})
    async with h.sessions() as session:
        version = await VersionsRepo(session).current()
    assert version is not None
    assert version.provenance is None


async def test_manual_review_over_an_existing_profile_is_a_manual_edit(make_harness: Any) -> None:
    h = make_harness([])
    async with h.sessions() as session:
        await VersionsRepo(session).create_version(typed("Old"), created_by="manual")
        await session.commit()
    run_id, _ = await start_manual(h)
    await h.run(run_id)

    await h.resume(run_id, {"action": "confirm", "content": content_to_json(typed("New"))})

    async with h.sessions() as session:
        versions = await VersionsRepo(session).list_versions()
    assert [v.created_by for v in versions] == ["manual_edit", "manual"]


async def test_manual_review_conflicts_with_an_open_review(make_harness: Any) -> None:
    h = make_harness([])
    run_id, _ = await start_manual(h)
    await h.run(run_id)
    review = await h.review()
    assert review is not None
    with pytest.raises(OpenReviewError) as caught:
        await start_manual(h)
    assert caught.value.open_review_id == review.id


async def test_FR041_active_run_blocks_unless_cancelled(make_harness: Any) -> None:
    h = make_harness([])
    uploaded = await h.start(PDF)  # queued import that never ran

    with pytest.raises(ActiveRunError) as caught:
        await start_manual(h)
    assert caught.value.active_run_id == uploaded

    run_id, queue = await start_manual(h, cancel=True)

    assert queue.jobs == [run_id]
    assert (await h.state(uploaded)).status is RunStatus.cancelled
    # a stale job for the cancelled run does nothing
    assert (await h.run(uploaded)).status is RunStatus.cancelled


async def test_FR041_a_paused_import_can_be_cancelled(make_harness: Any) -> None:
    from hiretitan.platform.llm.port import AiUnavailable

    h = make_harness([AiUnavailable("key_missing")])
    uploaded = await h.start(PDF)
    await h.run(uploaded)
    assert (await h.state(uploaded)).status is RunStatus.paused

    run_id, _ = await start_manual(h, cancel=True)

    assert (await h.state(uploaded)).status is RunStatus.cancelled
    assert (await h.run(run_id)).status is RunStatus.awaiting_review


async def test_a_running_import_cannot_be_cancelled(make_harness: Any) -> None:
    h = make_harness([])
    uploaded = await h.start(PDF)
    async with h.sessions() as session:
        await RunsRepo(session).transition(uploaded, RunStatus.running)
        await session.commit()
    with pytest.raises(ReadingInProgressError):
        await start_manual(h, cancel=True)
    assert (await h.state(uploaded)).status is RunStatus.running
