"""Outreach draft endpoints (T010, T013): US2, FR-008, FR-009, FR-010, FR-011, FR-014, EC-06."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.drafts_env import GOOD_CONNECTION, KEYWORDS, NOW, DraftsEnv, make_env

from hiretitan.api_main import create_app
from hiretitan.drafts.api.drafts import DraftsApiDeps, create_drafts_router
from hiretitan.drafts.infra.models import JobKeywordsRow, OutreachDraftRow
from hiretitan.drafts.workflow.outreach import run_outreach
from hiretitan.drafts_wiring import SqlContacts, clear_drafts_for_job
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo
from hiretitan.search_wiring import SqlResumeLookup


@dataclass
class Queue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.enqueued.append(run_id)


@dataclass
class Api:
    client: httpx.AsyncClient
    env: DraftsEnv
    queue: Queue


@pytest.fixture
async def api(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Api]:
    env = await make_env(sessions)
    queue = Queue()
    drafts = DraftsApiDeps(
        sessions=sessions,
        queue=queue,
        jobs=env.deps.jobs,
        profile=env.deps.profile,
        contacts=SqlContacts(sessions),
        provider="fake",
    )
    jobs = SearchJobsApiDeps(
        sessions=sessions,
        queue=queue,
        clock=FakeClock(NOW),
        resume_lookup=SqlResumeLookup,
        job_cleanups=(clear_drafts_for_job,),
    )
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[create_drafts_router(drafts), create_search_jobs_router(jobs)],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Api(client, env, queue)


def body(env: DraftsEnv, **over: Any) -> dict[str, Any]:
    return {
        "kind": "connection_request",
        "recipient": {"contact_id": str(env.contact_id)},
        **over,
    }


async def finish(api: Api, run_id: UUID, draft_id: UUID) -> None:
    api.env.llm.add(KEYWORDS, task="extract_job_keywords")
    api.env.llm.add(GOOD_CONNECTION, task="draft_connection_request")
    await run_outreach(api.env.deps, run_id, draft_id)


async def test_US2_AS1_recipients_list_company_contacts_with_kind(api: Api) -> None:
    res = await api.client.get(f"/api/v1/jobs/{api.env.job_id}/recipients")

    assert res.status_code == 200
    data = res.json()
    assert data["contacts"] == [
        {
            "contact_id": str(api.env.contact_id),
            "name": "Quillon Fairweather",
            "role": "Talent Partner",
            "kind": "recruiter",
        }
    ]
    assert data["kinds"] == ["recruiter", "hiring_manager", "engineer", "other"]


async def test_FR010_recipients_404_for_deleted_job(api: Api) -> None:
    assert (await api.client.delete(f"/api/v1/jobs/{api.env.job_id}")).status_code == 204

    assert (await api.client.get(f"/api/v1/jobs/{api.env.job_id}/recipients")).status_code == 404
    res = await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))
    assert res.status_code == 404


async def test_US2_AS1_draft_for_contact_or_typed_recipient(api: Api) -> None:
    contact = await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))
    typed = await api.client.post(
        f"/api/v1/jobs/{api.env.job_id}/drafts",
        json={
            "kind": "connection_request",
            "recipient": {"name": "  Asha   Rao ", "role": "Engineering Manager"},
        },
    )

    assert contact.status_code == typed.status_code == 202
    assert contact.json()["status"] == "writing"
    assert len(api.queue.enqueued) == 2
    listed = (await api.client.get(f"/api/v1/jobs/{api.env.job_id}/drafts")).json()["drafts"]
    names = {d["recipient"]["name"]: d["recipient"]["kind"] for d in listed}
    assert names == {"Quillon Fairweather": "recruiter", "Asha Rao": "hiring_manager"}
    assert all(d["status"] == "writing" and d["text"] is None for d in listed)


async def test_FR013_text_filled_with_first_name_by_the_workflow(api: Api) -> None:
    started = (
        await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))
    ).json()
    async with api.env.sessions() as session:
        run_id = (await session.get(OutreachDraftRow, UUID(started["id"]))).run_id  # type: ignore[union-attr]
    assert run_id is not None
    before = (await api.client.get(f"/api/v1/jobs/{api.env.job_id}/drafts")).json()["drafts"][0]
    assert before["text"] is None  # reading writes nothing

    await finish(api, run_id, UUID(started["id"]))

    draft = (await api.client.get(f"/api/v1/jobs/{api.env.job_id}/drafts")).json()["drafts"][0]
    assert draft["status"] == "ready"
    assert draft["text"].startswith("Hi Quillon,")
    assert draft["chars"] == len(draft["text"]) <= 200
    assert draft["cited_facts"] == [{"id": "skill:python", "text": "Python"}]


async def test_FR008_last_draft_kept_regenerate_on_request(api: Api) -> None:
    started = (
        await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))
    ).json()
    async with api.env.sessions() as session:
        run_id = (await session.get(OutreachDraftRow, UUID(started["id"]))).run_id  # type: ignore[union-attr]
    await finish(api, run_id, UUID(started["id"]))  # type: ignore[arg-type]

    again = await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))
    assert again.status_code == 200
    assert again.json()["status"] == "ready"
    assert len(api.queue.enqueued) == 1  # nothing was started

    redo = await api.client.post(
        f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env, regenerate=True)
    )
    assert redo.status_code == 202
    assert redo.json()["id"] == started["id"]
    assert len(api.queue.enqueued) == 2
    async with api.env.sessions() as session:
        count = await session.scalar(select(func.count()).select_from(OutreachDraftRow))
    assert count == 1  # one current draft per job, kind and recipient


async def test_EC06_draft_in_progress_409(api: Api) -> None:
    await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))

    res = await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))

    assert res.status_code == 409
    assert res.json()["reason"] == "draft_in_progress"


async def test_FR014_no_confirmed_profile_409(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    env = await make_env(sessions, with_profile=False)
    drafts = DraftsApiDeps(
        sessions=sessions,
        queue=Queue(),
        jobs=env.deps.jobs,
        profile=env.deps.profile,
        contacts=SqlContacts(sessions),
        provider="fake",
    )
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_drafts_router(drafts)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post(f"/api/v1/jobs/{env.job_id}/drafts", json=body(env))

    assert res.status_code == 409
    assert res.json()["reason"] == "no_confirmed_profile"


async def test_US2_AS6_ai_unavailable_409_with_reason(api: Api) -> None:
    async with api.env.sessions() as session:
        await ProviderStatusRepo(session).set("fake", "out_of_credit", "Your AI account is out.")
        await session.commit()

    res = await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))

    assert res.status_code == 409
    assert res.json()["reason"] == "ai_unavailable"
    assert "out" in res.json()["detail"]
    assert api.queue.enqueued == []


async def test_US2_AS6_paused_run_reason_is_shown_while_writing(api: Api) -> None:
    started = (
        await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))
    ).json()
    async with api.env.sessions() as session:
        row = await session.get(OutreachDraftRow, UUID(started["id"]))
        assert row is not None
        assert row.run_id is not None
        runs = RunsRepo(session)
        from hiretitan.platform.runtime.domain.run_state import PauseReason, RunStatus

        await runs.transition(row.run_id, RunStatus.running)
        await runs.transition(row.run_id, RunStatus.paused, pause_reason=PauseReason.out_of_credit)
        await session.commit()

    draft = (await api.client.get(f"/api/v1/jobs/{api.env.job_id}/drafts")).json()["drafts"][0]

    assert draft["status"] == "writing"
    assert draft["paused_reason"]


async def test_FR011_edit_over_200_saved_and_flagged(api: Api) -> None:
    started = (
        await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))
    ).json()
    async with api.env.sessions() as session:
        run_id = (await session.get(OutreachDraftRow, UUID(started["id"]))).run_id  # type: ignore[union-attr]
    await finish(api, run_id, UUID(started["id"]))  # type: ignore[arg-type]

    long = "x" * 230
    res = await api.client.put(f"/api/v1/drafts/{started['id']}", json={"text": long})

    assert res.status_code == 200
    data = res.json()
    assert data["text"] == long
    assert data["edited"] is True
    assert data["over_limit"] is True
    assert data["chars"] == 230
    assert (
        await api.client.put(f"/api/v1/drafts/{started['id']}", json={"text": ""})
    ).status_code == 422
    too_big = await api.client.put(f"/api/v1/drafts/{started['id']}", json={"text": "y" * 2001})
    assert too_big.status_code == 422


async def test_FR006_injection_signals_returned_and_shown(api: Api) -> None:
    async with api.env.sessions() as session:
        session.add(
            JobKeywordsRow(
                job_id=api.env.job_id,
                description_sha256="0" * 64,
                role_summary="x",
                keywords=[],
                must_have=[],
                injection_signals=[
                    {"rule_id": "ai_instruction", "severity": "high", "excerpt": "ignore all"}
                ],
                prompt_version="1",
                model="m",
            )
        )
        await session.commit()

    data = (await api.client.get(f"/api/v1/jobs/{api.env.job_id}/drafts")).json()

    assert data["injection_signals"] == [
        {"rule_id": "ai_instruction", "severity": "high", "excerpt": "ignore all"}
    ]


async def test_EC13_contact_from_another_company_404(api: Api) -> None:
    async with api.env.sessions() as session:
        other = await CompaniesRepo(session).add(name="Other", origin="user", resolution="verified")
        stranger = await ContactsRepo(session).add(
            other.id, ContactFields(name="Someone Else"), source="typed"
        )
        await session.commit()
        stranger_id = stranger.id

    res = await api.client.post(
        f"/api/v1/jobs/{api.env.job_id}/drafts",
        json={"kind": "connection_request", "recipient": {"contact_id": str(stranger_id)}},
    )
    missing = await api.client.post(
        f"/api/v1/jobs/{api.env.job_id}/drafts",
        json={"kind": "connection_request", "recipient": {"contact_id": str(uuid4())}},
    )

    assert res.status_code == missing.status_code == 404


async def test_EC02_bad_typed_recipient_422(api: Api) -> None:
    res = await api.client.post(
        f"/api/v1/jobs/{api.env.job_id}/drafts",
        json={"kind": "connection_request", "recipient": {"name": "   "}},
    )
    bad_kind = await api.client.post(
        f"/api/v1/jobs/{api.env.job_id}/drafts",
        json={"kind": "tweet", "recipient": {"name": "Asha"}},
    )

    assert res.status_code == bad_kind.status_code == 422


async def test_FR009_delete_draft_and_job_delete_removes_drafts(api: Api) -> None:
    started = (
        await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))
    ).json()
    async with api.env.sessions() as session:
        run_id = (await session.get(OutreachDraftRow, UUID(started["id"]))).run_id  # type: ignore[union-attr]
    await finish(api, run_id, UUID(started["id"]))  # type: ignore[arg-type]

    assert (await api.client.delete(f"/api/v1/drafts/{started['id']}")).status_code == 204
    assert (await api.client.delete(f"/api/v1/drafts/{started['id']}")).status_code == 404

    await api.client.post(
        f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env, regenerate=True)
    )
    assert (await api.client.delete(f"/api/v1/jobs/{api.env.job_id}")).status_code == 204
    async with api.env.sessions() as session:
        drafts = await session.scalar(select(func.count()).select_from(OutreachDraftRow))
        keywords = await session.scalar(select(func.count()).select_from(JobKeywordsRow))
    assert drafts == 0
    assert keywords == 0


async def test_FR009_delete_job_runs_cleanups(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    env = await make_env(sessions)
    seen: list[UUID] = []

    async def good(session: AsyncSession, job_id: UUID) -> None:
        seen.append(job_id)

    async def failing(session: AsyncSession, job_id: UUID) -> None:
        raise RuntimeError("clean-up failed")

    def build(cleanups: Any) -> httpx.AsyncClient:
        jobs = SearchJobsApiDeps(
            sessions=sessions,
            queue=Queue(),
            clock=FakeClock(NOW),
            resume_lookup=SqlResumeLookup,
            job_cleanups=cleanups,
        )
        app = create_app(
            Settings(), frontend_dist=tmp_path / "none", routers=[create_search_jobs_router(jobs)]
        )
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        )

    async with build((failing,)) as client:  # a failing clean-up rolls the delete back
        res = await client.delete(f"/api/v1/jobs/{env.job_id}")
        assert res.status_code == 500
    assert (await env.deps.jobs.get(env.job_id)) is not None

    async with build((good,)) as client:
        assert (await client.delete(f"/api/v1/jobs/{env.job_id}")).status_code == 204
    assert seen == [env.job_id]


async def test_EC06_two_clicks_at_once_give_one_draft_and_one_409(api: Api) -> None:
    import asyncio

    url = f"/api/v1/jobs/{api.env.job_id}/drafts"
    first, second = await asyncio.gather(
        api.client.post(url, json=body(api.env)), api.client.post(url, json=body(api.env))
    )
    assert sorted([first.status_code, second.status_code]) == [202, 409]


async def test_EC13_editing_a_failed_draft_makes_it_ready_and_strips_control_characters(
    api: Api,
) -> None:
    from hiretitan.drafts.infra.repos import DraftsRepo

    started = (
        await api.client.post(f"/api/v1/jobs/{api.env.job_id}/drafts", json=body(api.env))
    ).json()
    draft_id = UUID(started["id"])
    async with api.env.sessions() as session:
        await DraftsRepo(session).set_failed(draft_id, "Something went wrong.")
        await session.commit()

    res = await api.client.put(f"/api/v1/drafts/{draft_id}", json={"text": "Hi\x00 there\nThanks"})

    assert res.status_code == 200
    assert res.json()["status"] == "ready"
    assert res.json()["text"] == "Hi there\nThanks"
