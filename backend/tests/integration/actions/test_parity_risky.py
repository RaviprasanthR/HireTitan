"""002m T025: Mikasa's risky changes to jobs, searches and mail go through a confirm card and do
what the UI does (FR-006, FR-010, US2 scenario 8, EC-11, EC-12)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.mail_env import make_run

from hiretitan.actions.registry import build_catalogue
from hiretitan.actions.spec import ActionServices
from hiretitan.api_main import create_app
from hiretitan.assistant.application.cards import CardFailedError, confirm_card
from hiretitan.assistant.application.changes import undo_change
from hiretitan.assistant.application.ports import ApplyOutcome, CallContext, ToolOutcome
from hiretitan.assistant.infra.repos import ConversationsRepo, MessagesRepo
from hiretitan.assistant_wiring import CatalogAdapter, card_units, undo_units
from hiretitan.mail.application.ports import CheckNotReadyError
from hiretitan.mail.infra.models import MailSenderRow
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.search.api.jobs import SearchJobsApiDeps, create_search_jobs_router
from hiretitan.search.infra.models import JobRow, PossibleDuplicateRow
from hiretitan.search.infra.repos import CompaniesRepo, DecisionsRepo, DuplicatesRepo, JobsRepo
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
    queue: Queue
    services: ActionServices
    conversation: UUID
    message: UUID

    async def propose(self, action: str, **args: Any) -> ToolOutcome:
        adapter = CatalogAdapter(build_catalogue(), self.sessions, self.services)
        return await adapter.call(
            action,
            json.dumps(args, default=str),
            CallContext(self.conversation, NOW, message_id=self.message),
        )

    async def confirm(self, outcome: ToolOutcome) -> ApplyOutcome:
        assert outcome.card is not None, outcome.payload
        units = card_units(build_catalogue(), self.sessions, lambda: NOW, self.services)
        return await confirm_card(units, outcome.card.card_id, {}, NOW)

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
            )
            await DecisionsRepo(session).record(
                row.id, outcome="shown", decided_by="rules_only_fallback", reason="rules only"
            )
            await session.commit()
            return row.id

    async def state(self, job_id: UUID) -> tuple[Any, ...]:
        async with self.sessions() as session:
            row = await session.get(JobRow, job_id)
            assert row is not None
            return (row.state, row.applied_on)


started: list[str] = []


async def fake_start_search(session: AsyncSession, mode: str, now: datetime) -> UUID:
    started.append(mode)
    return uuid4()


async def mail_not_connected(now: datetime, reread: bool) -> UUID:
    raise CheckNotReadyError("not_connected")


@pytest.fixture
async def world(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[World]:
    started.clear()
    queue = Queue()
    services = ActionServices(
        queue=queue, start_search=fake_start_search, start_mail_check=mail_not_connected
    )
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_search_jobs_router(
                SearchJobsApiDeps(
                    sessions=sessions,
                    queue=queue,
                    clock=FakeClock(NOW),
                    resume_lookup=SqlResumeLookup,
                )
            )
        ],
    )
    async with sessions() as session:
        conversation = await ConversationsRepo(session).create(now=NOW)
        message = await MessagesRepo(session).append(
            conversation.id, author="person", text="do it", now=NOW
        )
        await session.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield World(sessions, client, queue, services, conversation.id, message.id)


async def test_FR006_parity_delete_job(world: World) -> None:
    mine, theirs = await world.job(), await world.job()

    outcome = await world.propose("delete_job", job=f"job:{mine}")
    assert outcome.card is not None
    assert outcome.card.summary == "Delete: Backend Engineer at Acme"
    assert (await world.state(mine))[0] == "explore"  # nothing yet
    await world.confirm(outcome)
    await world.client.delete(f"/api/v1/jobs/{theirs}")

    assert await world.state(mine) == await world.state(theirs) == ("deleted", None)


async def test_FR006_parity_recheck_queued_after_commit(world: World) -> None:
    job_id = await world.job()

    applied = await world.confirm(await world.propose("recheck_job", job=f"job:{job_id}"))

    assert len(world.queue.enqueued) == 1
    assert applied.results[0]["summary"] == "Asked the AI to check Backend Engineer at Acme."


async def test_FR006_parity_merge_and_dismiss(world: World) -> None:
    a, b, c = await world.job(), await world.job("applied"), await world.job()
    async with world.sessions() as session:
        await DuplicatesRepo(session).add(a, b, similarity=0.95)
        await DuplicatesRepo(session).add(a, c, similarity=0.9)
        await session.commit()
        pairs = {
            frozenset((p.job_a_id, p.job_b_id)): p.id
            for p in await session.scalars(select(PossibleDuplicateRow))
        }

    await world.confirm(
        await world.propose("merge_duplicate", duplicate=f"duplicate:{pairs[frozenset((a, b))]}")
    )
    await world.confirm(
        await world.propose("dismiss_duplicate", duplicate=f"duplicate:{pairs[frozenset((a, c))]}")
    )

    kept, gone = sorted((a, b))
    assert (await world.state(kept))[0] == "applied"  # the stronger state is kept
    assert (await world.state(gone))[0] == "deleted"
    async with world.sessions() as session:
        statuses = {p.id: p.status for p in await session.scalars(select(PossibleDuplicateRow))}
    assert sorted(statuses.values()) == ["dismissed", "merged"]


async def test_US2_AS8_bulk_marks_each_undoable(world: World) -> None:
    jobs = [await world.job(title=f"Engineer {n}") for n in range(3)]

    outcome = await world.propose("mark_applied_many", jobs=[f"job:{j}" for j in jobs])
    applied = await world.confirm(outcome)

    assert [await world.state(j) for j in jobs] == [("applied", date(2026, 11, 24))] * 3
    assert len(applied.results) == 3
    assert all(r["undoable"] for r in applied.results)
    units = undo_units(build_catalogue(), world.sessions, lambda: NOW)
    await undo_change(units, UUID(applied.results[1]["change_id"]), NOW)
    assert [await world.state(j) for j in jobs] == [
        ("applied", date(2026, 11, 24)),
        ("explore", None),
        ("applied", date(2026, 11, 24)),
    ]


async def test_EC11_search_running_reported(
    world: World, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        await make_run(session, mode="rules_only")  # not finished: it is running
        await session.commit()

    outcome = await world.propose("start_search")

    assert outcome.card is None
    assert outcome.payload["error"] == "search_already_running"
    assert "companies read" in outcome.payload["message"]
    assert started == []


async def test_FR006_start_search_through_its_use_case(world: World) -> None:
    applied = await world.confirm(await world.propose("start_search", mode="rules_only"))

    assert started == ["rules_only"]
    assert applied.results[0]["summary"] == "Started a search."


async def test_EC12_mail_check_when_not_connected(world: World) -> None:
    outcome = await world.propose("start_mail_check")

    with pytest.raises(CardFailedError) as caught:
        await world.confirm(outcome)

    assert "Settings → Gmail" in str(caught.value)


async def test_FR006_mail_senders(world: World) -> None:
    added = await world.confirm(
        await world.propose("add_mail_sender", address="jobs@alerts.example.com")
    )
    async with world.sessions() as session:
        row = (
            await session.scalars(
                select(MailSenderRow).where(MailSenderRow.address == "jobs@alerts.example.com")
            )
        ).one()
    sender = f"sender:{row.id}"

    await world.confirm(await world.propose("switch_mail_sender", sender=sender, enabled=False))
    async with world.sessions() as session:
        switched = await session.get(MailSenderRow, row.id)
        assert switched is not None
        assert switched.enabled is False
    await world.confirm(await world.propose("remove_mail_sender", sender=sender))

    assert added.results[0]["summary"] == "Added the alert sender."
    async with world.sessions() as session:
        assert await session.get(MailSenderRow, row.id) is None
