"""002m T032 (US3): Mikasa's drafts and tailored resume go through a confirm card and the same
use cases as the job page (FR-006, FR-008a, FR-009, FR-010, SC-010)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.drafts_env import CONTACT_NAME, NOW, DraftsEnv, make_env

from hiretitan.actions.cards import describe
from hiretitan.actions.catalogue import EXCLUDED
from hiretitan.actions.registry import build_catalogue
from hiretitan.actions.spec import ActionServices
from hiretitan.api_main import create_app
from hiretitan.assistant.application.cards import CardFailedError, confirm_card
from hiretitan.assistant.application.ports import ApplyOutcome, CallContext, ToolOutcome
from hiretitan.assistant.infra.repos import ConversationsRepo, MessagesRepo
from hiretitan.assistant_wiring import CatalogAdapter, action_services, card_units
from hiretitan.drafts.api.drafts import DraftsApiDeps, create_drafts_router
from hiretitan.drafts.api.resumes import create_resumes_router
from hiretitan.drafts.infra.models import OutreachDraftRow, TailoredResumeRow
from hiretitan.drafts_wiring import SqlContacts
from hiretitan.platform.config.settings import Settings


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
    env: DraftsEnv
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

    async def drafts(self) -> list[OutreachDraftRow]:
        async with self.sessions() as session:
            return list(await session.scalars(select(OutreachDraftRow)))


async def _build(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path, *, with_profile: bool
) -> AsyncIterator[World]:
    env = await make_env(sessions, with_profile=with_profile)
    queue = Queue()
    services = action_services(
        sessions,
        queue=queue,
        clock=None,
        synonyms={},
        work_areas=None,
        careers=None,
        provider="fake",
    )
    deps = DraftsApiDeps(
        sessions=sessions,
        queue=queue,
        jobs=env.deps.jobs,
        profile=env.deps.profile,
        contacts=SqlContacts(sessions),
        provider="fake",
    )
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[create_drafts_router(deps), create_resumes_router(deps)],
    )
    async with sessions() as session:
        conversation = await ConversationsRepo(session).create(now=NOW)
        message = await MessagesRepo(session).append(
            conversation.id, author="person", text="write it", now=NOW
        )
        await session.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield World(sessions, client, queue, services, env, conversation.id, message.id)


@pytest.fixture
async def world(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[World]:
    async for w in _build(sessions, tmp_path, with_profile=True):
        yield w


@pytest.fixture
async def bare(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[World]:
    async for w in _build(sessions, tmp_path, with_profile=False):
        yield w


async def test_US3_AS1_draft_through_002k_action(world: World) -> None:
    job = f"job:{world.env.job_id}"

    outcome = await world.propose("draft_connection_request", job=job)
    assert outcome.card is not None
    assert await world.drafts() == []  # nothing is written until the card is confirmed

    applied = await world.confirm(outcome)

    rows = await world.drafts()
    assert len(rows) == 1
    assert (rows[0].kind, rows[0].status) == ("connection_request", "writing")
    assert rows[0].recipient_name == "Hiring team"  # no name given: the hiring team
    assert applied.results[0]["refs"] == [f"draft:{rows[0].id}"]
    assert len(world.queue.enqueued) == 1  # queued for the worker, as the job page does


async def test_FR009_draft_saved_where_job_page_shows_it(world: World) -> None:
    await world.confirm(
        await world.propose(
            "draft_referral_message", job=f"job:{world.env.job_id}", name="Dana Osei"
        )
    )

    shown = (await world.client.get(f"/api/v1/jobs/{world.env.job_id}/drafts")).json()

    assert [(d["kind"], d["recipient"]["name"]) for d in shown["drafts"]] == [
        ("referral_message", "Dana Osei")
    ]


async def test_SC010_contact_recipient_not_sent(world: World) -> None:
    contact = f"contact:{world.env.contact_id}"

    outcome = await world.propose(
        "draft_connection_request", job=f"job:{world.env.job_id}", contact=contact
    )
    assert outcome.card is not None
    await world.confirm(outcome)

    # the card, the model's result and the list name the contact by ref and by company only
    assert CONTACT_NAME not in json.dumps(outcome.payload, default=str)
    assert CONTACT_NAME not in outcome.card.summary
    listed = await world.propose("list_drafts", job=f"job:{world.env.job_id}")
    assert CONTACT_NAME not in json.dumps(listed.payload, default=str)
    [row] = await world.drafts()
    assert row.recipient_contact_id == world.env.contact_id  # resolved on the server


async def test_US3_contact_of_another_company_is_refused(world: World) -> None:
    outcome = await world.propose(
        "draft_connection_request",
        job=f"job:{world.env.job_id}",
        contact="contact:00000000-0000-0000-0000-000000000001",
    )

    assert outcome.card is None


async def test_US3_AS2_tailored_resume_linked(world: World) -> None:
    applied = await world.confirm(
        await world.propose("tailor_resume", job=f"job:{world.env.job_id}")
    )

    async with world.sessions() as session:
        row = (await session.scalars(select(TailoredResumeRow))).one()
        card = await describe(session, f"tailored_resume:{row.id}")
    assert applied.results[0]["refs"] == [f"tailored_resume:{row.id}"]
    assert card is not None
    assert card.link == f"/jobs/{world.env.job_id}/resume"
    assert "writing" in (card.subtitle or "")
    assert len(world.queue.enqueued) == 1


async def test_US3_no_profile_says_so(bare: World) -> None:
    outcome = await bare.propose("tailor_resume", job=f"job:{bare.env.job_id}")

    with pytest.raises(CardFailedError) as raised:
        await bare.confirm(outcome)

    assert "profile" in str(raised.value).casefold()
    assert bare.queue.enqueued == []


async def test_FR008a_no_action_edits_draft_text() -> None:
    catalogue = build_catalogue()
    names = {spec.name for spec in catalogue.specs()}
    assert {"edit_draft", "edit_tailored_resume", "update_draft"}.isdisjoint(names)
    mirrored = {m for spec in catalogue.specs() for m in spec.mirrors}
    edits = {"PUT /drafts/{draft_id}", "PUT /jobs/{job_id}/tailored-resume"}
    assert mirrored.isdisjoint(edits)
    assert edits <= set(EXCLUDED)


async def test_FR006_parity_delete_draft_and_resume(world: World) -> None:
    await world.confirm(
        await world.propose("draft_referral_message", job=f"job:{world.env.job_id}")
    )
    await world.confirm(await world.propose("tailor_resume", job=f"job:{world.env.job_id}"))
    # both are "writing" now: neither can be deleted until finished, as on the job page
    [draft] = await world.drafts()
    busy = await world.propose("delete_draft", draft=f"draft:{draft.id}")
    with pytest.raises(CardFailedError):
        await world.confirm(busy)
    async with world.sessions() as session:
        row = await session.get(OutreachDraftRow, draft.id)
        assert row is not None
        row.status = "ready"
        resume = (await session.scalars(select(TailoredResumeRow))).one()
        resume.status = "ready"
        await session.commit()

    await world.confirm(await world.propose("delete_draft", draft=f"draft:{draft.id}"))
    await world.confirm(
        await world.propose("delete_tailored_resume", job=f"job:{world.env.job_id}")
    )

    assert await world.drafts() == []
    gone = await world.client.get(f"/api/v1/jobs/{world.env.job_id}/tailored-resume")
    assert gone.status_code == 404
