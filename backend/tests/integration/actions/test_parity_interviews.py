"""002m T023: Mikasa's small changes to interview details and the resume used do what the job
page does (FR-006), can be undone (FR-014), and give the model nothing private (FR-022)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
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
from hiretitan.assistant.application.changes import undo_change
from hiretitan.assistant.application.ports import CallContext, ToolOutcome
from hiretitan.assistant.infra.repos import ConversationsRepo, MessagesRepo
from hiretitan.assistant_wiring import CatalogAdapter, undo_units
from hiretitan.platform.config.settings import Settings
from hiretitan.profile.infra.repos import ResumeFilesRepo
from hiretitan.search.api.interviews import SearchInterviewsApiDeps, create_interviews_router
from hiretitan.search.infra.models import (
    InterviewQuestionRow,
    InterviewRoundRow,
    PipelineDetailsRow,
)
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo
from hiretitan.search_wiring import SqlResumeLookup

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
PRIVATE = ("Philippa Vossberg", "philippa@example.invalid", "Hirequest", "Ottoline", "feedback-77")


@dataclass
class World:
    sessions: async_sessionmaker[AsyncSession]
    client: httpx.AsyncClient
    adapter: CatalogAdapter
    conversation: UUID
    message: UUID

    async def call(self, action: str, **args: Any) -> ToolOutcome:
        outcome = await self.adapter.call(
            action,
            json.dumps(args, default=str),
            CallContext(self.conversation, NOW, message_id=self.message),
        )
        seen = json.dumps(outcome.payload)
        for value in PRIVATE:
            assert value not in seen, value  # FR-022: the model never gets the values back
        return outcome

    async def job(self) -> UUID:
        async with self.sessions() as session:
            company = await CompaniesRepo(session).add(
                name="Acme", origin="user", resolution="verified"
            )
            row = await JobsRepo(session).add(
                company_id=company.id,
                company_name="Acme",
                title="Backend Engineer",
                first_seen_at=NOW,
                last_seen_at=NOW,
                description="",
                state="applied",
                applied_on=date(2026, 11, 20),
            )
            await session.commit()
            return row.id

    async def details(self, job_id: UUID, names: tuple[str, ...]) -> tuple[Any, ...]:
        async with self.sessions() as session:
            row = await session.get(PipelineDetailsRow, job_id)
            return tuple(getattr(row, n) if row else None for n in names)

    async def undo(self, outcome: ToolOutcome) -> None:
        assert outcome.change is not None, outcome.payload
        await undo_change(
            undo_units(build_catalogue(), self.sessions, lambda: NOW), outcome.change.change_id, NOW
        )


@pytest.fixture
async def world(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[World]:
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_interviews_router(
                SearchInterviewsApiDeps(sessions=sessions, resume_lookup=SqlResumeLookup)
            )
        ],
    )
    async with sessions() as session:
        conversation = await ConversationsRepo(session).create(now=NOW)
        message = await MessagesRepo(session).append(
            conversation.id, author="person", text="Round 2 on Friday", now=NOW
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


CONTACT = ("contact_name", "contact_email")


async def test_FR006_parity_set_interview_contact_and_source(world: World) -> None:
    mine, theirs = await world.job(), await world.job()

    contact = await world.call(
        "set_interview_contact",
        job=f"job:{mine}",
        name="Philippa Vossberg",
        email="philippa@example.invalid",
    )
    await world.client.put(
        f"/api/v1/jobs/{theirs}/interview/contact",
        json={"name": "Philippa Vossberg", "email": "philippa@example.invalid"},
    )
    source = await world.call(
        "set_interview_source", job=f"job:{mine}", kind="hiring_firm", firm_name="Hirequest"
    )
    await world.client.put(
        f"/api/v1/jobs/{theirs}/interview/source",
        json={"kind": "hiring_firm", "firm_name": "Hirequest"},
    )

    both = (*CONTACT, "source", "firm_name")
    assert await world.details(mine, both) == await world.details(theirs, both)
    assert contact.payload["done"] == "Saved the point of contact for Backend Engineer at Acme."

    await world.undo(source)
    await world.undo(contact)
    assert await world.details(mine, both) == (None, None, None, None)


async def test_FR006_parity_rounds_and_questions(world: World) -> None:
    mine, theirs = await world.job(), await world.job()

    added = await world.call(
        "add_round", job=f"job:{mine}", kind="technical", interviewers="Ottoline"
    )
    await world.client.post(
        f"/api/v1/jobs/{theirs}/interview/rounds",
        json={"kind": "technical", "interviewers": "Ottoline"},
    )
    async with world.sessions() as session:
        rounds = {r.job_id: r for r in await session.scalars(select(InterviewRoundRow))}
    mine_round, their_round = rounds[mine], rounds[theirs]
    assert added.refs == [f"round:{mine_round.id}"]

    edited = await world.call(
        "edit_round", round=f"round:{mine_round.id}", state="cleared", feedback="feedback-77"
    )
    await world.client.patch(
        f"/api/v1/interview/rounds/{their_round.id}",
        json={"state": "cleared", "feedback": "feedback-77"},
    )
    asked = await world.call(
        "add_question", round=f"round:{mine_round.id}", question="Why Postgres?", answer="MVCC"
    )
    await world.client.post(
        f"/api/v1/interview/rounds/{their_round.id}/questions",
        json={"question": "Why Postgres?", "answer": "MVCC"},
    )
    async with world.sessions() as session:
        a = await session.get(InterviewRoundRow, mine_round.id)
        b = await session.get(InterviewRoundRow, their_round.id)
        assert a is not None
        assert b is not None
        assert (a.kind, a.state, a.feedback, a.number) == (b.kind, b.state, b.feedback, b.number)
        questions = list(await session.scalars(select(InterviewQuestionRow)))
        assert len(questions) == 2

    reworded = await world.call("edit_question", question_ref=asked.refs[0], answer="Snapshots")
    await world.undo(reworded)
    await world.undo(asked)
    await world.undo(edited)
    async with world.sessions() as session:
        back = await session.get(InterviewRoundRow, mine_round.id)
        assert back is not None
        assert (back.state, back.feedback) == ("scheduled", None)
        assert len(list(await session.scalars(select(InterviewQuestionRow)))) == 1
    await world.undo(added)
    async with world.sessions() as session:
        assert await session.get(InterviewRoundRow, mine_round.id) is None


async def test_FR006_parity_set_resume_used(world: World) -> None:
    mine, theirs = await world.job(), await world.job()
    async with world.sessions() as session:
        file = await ResumeFilesRepo(session).create(
            kind="upload_pdf", original_name="resume.pdf", size_bytes=10, sha256="d" * 64
        )
        await session.commit()

    chosen = await world.call(
        "set_resume_used", job=f"job:{mine}", resume_file=f"resume_file:{file.id}"
    )
    response = await world.client.put(
        f"/api/v1/jobs/{theirs}/interview/resume", json={"resume_file_id": str(file.id)}
    )

    assert response.status_code == 200
    names = ("resume_file_id", "resume_name")
    assert await world.details(mine, names) == await world.details(theirs, names)
    await world.undo(chosen)
    assert await world.details(mine, names) == (None, None)


async def test_FR006_round_refused_like_the_page(world: World) -> None:
    job_id = await world.job()
    first = await world.call("add_round", job=f"job:{job_id}", kind="technical")
    await world.call("edit_round", round=first.refs[0], state="failed")

    refused = await world.call("add_round", job=f"job:{job_id}", kind="hr")
    page = await world.client.post(f"/api/v1/jobs/{job_id}/interview/rounds", json={"kind": "hr"})

    assert refused.payload["error"] == "process_failed"
    assert page.status_code == 409
