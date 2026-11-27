"""002m T021: Mikasa's small job changes do what the UI's endpoints do (FR-006), apply at once
with an Undo (US2 scenarios 1 to 3, FR-014), and never open a job link (FR-008, constitution VII).

Each parity test applies the action to one job and calls the endpoint for an identical job, then
compares the stored result.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.actions.registry import build_catalogue
from hiretitan.api_main import create_app
from hiretitan.assistant.application.changes import UndoRefusedError, undo_change
from hiretitan.assistant.application.ports import CallContext, ToolOutcome
from hiretitan.assistant.infra.repos import ConversationsRepo, MessagesRepo
from hiretitan.assistant_wiring import CatalogAdapter, undo_units
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.companies import SearchCompaniesApiDeps, create_companies_router
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.models import CompanyRow, ContactRow, JobRow
from hiretitan.search.infra.repos import CompaniesRepo, DecisionsRepo, JobsRepo, NotesRepo
from hiretitan.search_wiring import SqlResumeLookup

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)


@dataclass
class Queue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.enqueued.append(run_id)


@dataclass
class World:
    sessions: async_sessionmaker[AsyncSession]
    client: httpx.AsyncClient
    adapter: CatalogAdapter
    conversation: UUID
    message: UUID

    async def call(self, action: str, **args: Any) -> ToolOutcome:
        return await self.adapter.call(
            action,
            json.dumps(args, default=str),
            CallContext(self.conversation, NOW, message_id=self.message),
        )

    async def job(self, state: str = "explore", title: str = "Backend Engineer") -> UUID:
        async with self.sessions() as session:
            company = await CompaniesRepo(session).add(
                name="Acme", origin="user", resolution="verified"
            )
            row = await JobsRepo(session).add(
                company_id=company.id,
                company_name="Acme",
                title=title,
                first_seen_at=NOW,
                last_seen_at=NOW,
                description="",
                state=state,
                applied_on=date(2026, 11, 20) if state == "applied" else None,
                inquired_on=date(2026, 11, 20) if state == "inquired" else None,
            )
            if state == "skipped":
                await DecisionsRepo(session).record(
                    row.id, outcome="skipped", decided_by="rule", reason="Title has Java"
                )
            await session.commit()
            return row.id

    async def fields(self, job_id: UUID) -> tuple[Any, ...]:
        async with self.sessions() as session:
            row = await session.get(JobRow, job_id)
            assert row is not None
            return (row.state, row.applied_on, row.inquired_on, row.restored)


@pytest.fixture
async def world(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[World]:
    deps = SearchJobsApiDeps(
        sessions=sessions,
        queue=Queue(),
        clock=FakeClock(NOW),
        resume_lookup=SqlResumeLookup,
        job_cleanups=(),
    )
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_search_jobs_router(deps)]
    )
    async with sessions() as session:
        conversation = await ConversationsRepo(session).create(now=NOW)
        message = await MessagesRepo(session).append(
            conversation.id, author="person", text="I applied", now=NOW
        )
        await session.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield World(
            sessions,
            client,
            CatalogAdapter(build_catalogue(), sessions),
            conversation.id,
            message.id,
        )


@pytest.mark.parametrize(
    ("action", "start", "method", "path"),
    [
        ("mark_applied", "explore", "POST", "applied"),
        ("mark_inquired", "explore", "POST", "inquired"),
        ("unmark_applied", "applied", "DELETE", "applied"),
        ("unmark_inquired", "inquired", "DELETE", "inquired"),
        ("restore_job", "skipped", "POST", "restore"),
    ],
)
async def test_FR006_parity_job_changes(
    world: World, action: str, start: str, method: str, path: str
) -> None:
    by_mikasa = await world.job(start)
    by_page = await world.job(start)

    outcome = await world.call(action, job=f"job:{by_mikasa}")
    response = await world.client.request(method, f"/api/v1/jobs/{by_page}/{path}")

    assert outcome.valid
    assert outcome.change is not None, outcome.payload
    assert response.status_code == 200
    assert await world.fields(by_mikasa) == await world.fields(by_page)


@pytest.mark.parametrize(
    ("action", "start", "method", "path", "reason"),
    [
        ("mark_applied", "applied", "POST", "applied", "already_applied"),
        ("mark_inquired", "applied", "POST", "inquired", "already_applied"),
        ("unmark_applied", "explore", "DELETE", "applied", "not_applied"),
        ("restore_job", "explore", "POST", "restore", "not_skipped"),
    ],
)
async def test_FR006_parity_refusals(
    world: World, action: str, start: str, method: str, path: str, reason: str
) -> None:
    by_mikasa = await world.job(start)
    by_page = await world.job(start)

    outcome = await world.call(action, job=f"job:{by_mikasa}")
    response = await world.client.request(method, f"/api/v1/jobs/{by_page}/{path}")

    assert outcome.payload["error"] == reason
    assert response.status_code == 409
    assert response.json()["reason"] == reason
    assert outcome.change is None


async def test_US2_AS1_mark_applied_at_once_with_undo(world: World) -> None:
    job_id = await world.job("inquired")

    outcome = await world.call("mark_applied", job=f"job:{job_id}")

    assert outcome.change is not None
    assert outcome.change.summary == "Marked Backend Engineer at Acme as applied on 2026-11-24."
    assert (await world.fields(job_id))[:2] == ("applied", date(2026, 11, 24))

    await undo_change(
        undo_units(build_catalogue(), world.sessions, lambda: NOW), outcome.change.change_id, NOW
    )

    # the exact earlier state comes back, the inquiry and its date included (FR-014)
    assert await world.fields(job_id) == ("inquired", None, date(2026, 11, 20), False)


async def test_US2_AS2_link_added_once_and_marked(world: World) -> None:
    link = "https://jobs.example.com/acme/123"

    outcome = await world.call(
        "add_job_and_mark", url=link, title="Backend Engineer", company="Acme", mark="applied"
    )
    again = await world.call("add_job", url=link, title="Backend Engineer", company="Acme")

    assert outcome.change is not None
    async with world.sessions() as session:
        jobs = list(await session.scalars(select(JobRow)))
    assert len(jobs) == 1
    assert (jobs[0].state, jobs[0].applied_on, jobs[0].description) == (
        "applied",
        date(2026, 11, 24),
        "",
    )
    assert again.payload["error"] == "already_in_hiretitan"
    assert f"job:{jobs[0].id}" in again.payload["message"]


async def test_R6_undo_of_add_allows_readding(world: World) -> None:
    link = "https://jobs.example.com/acme/123"
    added = await world.call("add_job", url=link, title="Backend Engineer", company="Acme")
    assert added.change is not None

    await undo_change(
        undo_units(build_catalogue(), world.sessions, lambda: NOW), added.change.change_id, NOW
    )

    async with world.sessions() as session:
        assert (await session.scalars(select(JobRow))).all() == []
    again = await world.call("add_job", url=link, title="Backend Engineer", company="Acme")
    assert again.change is not None  # not refused as "deleted earlier"


async def test_R6_undo_of_add_refused_once_details_were_added(world: World) -> None:
    added = await world.call(
        "add_job_and_mark",
        url="https://jobs.example.com/acme/9",
        title="Backend Engineer",
        company="Acme",
    )
    assert added.change is not None
    async with world.sessions() as session:  # the person adds a round on the job's page
        job_id = (await session.scalars(select(JobRow.id))).one()
        await InterviewsRepo(session).add_round(job_id, kind="technical")
        await session.commit()

    with pytest.raises(UndoRefusedError) as caught:
        await undo_change(
            undo_units(build_catalogue(), world.sessions, lambda: NOW), added.change.change_id, NOW
        )
    assert caught.value.reason == "changed_since"


async def test_US2_AS3_blocked_site_not_fetched(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_requests(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("HireTitan must not open a job link")

    monkeypatch.setattr(httpx.AsyncClient, "send", no_requests)
    monkeypatch.setattr(httpx.Client, "send", no_requests)
    try:
        import httpx2

        monkeypatch.setattr(httpx2.AsyncClient, "send", no_requests)
    except ImportError:
        pass

    for link in ("https://www.linkedin.com/jobs/view/123", "https://www.naukri.com/job/456"):
        looked_up = await world.adapter.call(
            "find_job_by_link", json.dumps({"url": link}), CallContext(world.conversation, NOW)
        )
        added = await world.call("add_job", url=link, title="Engineer", company="Globex")
        assert looked_up.payload["items"][0]["found"] is False
        assert added.change is not None


async def company(world: World, name: str = "Acme") -> UUID:
    async with world.sessions() as session:
        row = await CompaniesRepo(session).add(name=name, origin="user", resolution="unresolved")
        await session.commit()
        return row.id


async def test_FR006_parity_add_and_edit_company(
    world: World, sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_companies_router(
                SearchCompaniesApiDeps(sessions=sessions, clock=FakeClock(NOW), careers=None)  # type: ignore[arg-type]
            )
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        added = await world.call("add_company", name="Freshworks", city="Chennai")
        page = await client.post("/api/v1/companies", json={"name": "Zoho", "city": "Chennai"})
        assert added.change is not None
        assert page.status_code == 201
        async with sessions() as session:
            rows = {r.name: r for r in await session.scalars(select(CompanyRow))}
        mine, theirs = rows["Freshworks"], rows["Zoho"]
        assert (mine.origin, mine.resolution, mine.city) == (
            theirs.origin,
            theirs.resolution,
            theirs.city,
        )

        edited = await world.call(
            "edit_company", company=f"company:{mine.id}", city="Pune", hidden=True
        )
        page_edit = await client.patch(
            f"/api/v1/companies/{theirs.id}", json={"city": "Pune", "hidden": True}
        )
        assert edited.change is not None
        assert page_edit.status_code == 200
        async with sessions() as session:
            a = await session.get(CompanyRow, mine.id)
            b = await session.get(CompanyRow, theirs.id)
            assert a is not None
            assert b is not None
            assert (a.city, a.hidden, a.user_modified) == (b.city, b.hidden, b.user_modified)

        await undo_change(
            undo_units(build_catalogue(), sessions, lambda: NOW), edited.change.change_id, NOW
        )
        async with sessions() as session:
            back = await session.get(CompanyRow, mine.id)
            assert back is not None
            assert (back.city, back.hidden, back.user_modified) == ("Chennai", False, False)


async def test_EC15_typed_contact_saved_then_private(world: World) -> None:
    company_id = await company(world)

    added = await world.call(
        "add_contact",
        company=f"company:{company_id}",
        name="Zebulon Quarrington",
        email="zebulon.private@example.invalid",
    )
    edited = await world.call("edit_contact", contact=added.refs[0], phone="+1 555 0177")
    noted = await world.call(
        "set_company_note", company=f"company:{company_id}", text="note-distinctive-4410"
    )

    for outcome in (added, edited, noted):
        assert outcome.change is not None, outcome.payload
        seen = json.dumps(outcome.payload)
        for private in ("Zebulon", "zebulon.private", "+1 555 0177", "note-distinctive-4410"):
            assert private not in seen
    assert added.payload["done"] == "Added a contact at Acme."
    async with world.sessions() as session:
        contact = (await session.scalars(select(ContactRow))).one()
        assert (contact.name, contact.phone) == ("Zebulon Quarrington", "+1 555 0177")

    units = undo_units(build_catalogue(), world.sessions, lambda: NOW)
    assert noted.change is not None
    assert edited.change is not None
    await undo_change(units, noted.change.change_id, NOW)
    await undo_change(units, edited.change.change_id, NOW)
    async with world.sessions() as session:
        contact = (await session.scalars(select(ContactRow))).one()
        assert contact.phone is None
        assert await NotesRepo(session).get(company_id) is None
