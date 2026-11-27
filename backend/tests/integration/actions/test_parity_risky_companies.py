"""002m T026: Mikasa's risky changes to companies, contacts, interview details and the resume
used go through a confirm card, do what the pages do (FR-006), and give the model nothing private
(FR-022)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.career_ops import FakeCareerOps

from hiretitan.actions.registry import build_catalogue
from hiretitan.actions.spec import ActionServices
from hiretitan.assistant.application.cards import confirm_card
from hiretitan.assistant.application.ports import ApplyOutcome, CallContext, ToolOutcome
from hiretitan.assistant.infra.repos import ConversationsRepo, MessagesRepo
from hiretitan.assistant_wiring import CatalogAdapter, card_units
from hiretitan.profile.infra.repos import ResumeFilesRepo
from hiretitan.search.application.ports import DiscoveryResult
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.models import (
    CompanyRow,
    ContactRow,
    InterviewQuestionRow,
    InterviewRoundRow,
    PipelineDetailsRow,
)
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, JobsRepo

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
PRIVATE = ("Zebulon", "zeb@example.invalid", "Ottoline", "secret-question-41", "cv-file-55.pdf")


@dataclass
class World:
    sessions: async_sessionmaker[AsyncSession]
    services: ActionServices
    conversation: UUID
    message: UUID

    async def run(self, action: str, **args: Any) -> tuple[ToolOutcome, ApplyOutcome]:
        adapter = CatalogAdapter(build_catalogue(), self.sessions, self.services)
        outcome = await adapter.call(
            action,
            json.dumps(args, default=str),
            CallContext(self.conversation, NOW, message_id=self.message),
        )
        seen = json.dumps(outcome.payload)
        for value in PRIVATE:
            assert value not in seen, value
        assert outcome.card is not None, outcome.payload
        units = card_units(build_catalogue(), self.sessions, lambda: NOW, self.services)
        return outcome, await confirm_card(units, outcome.card.card_id, {}, NOW)


@pytest.fixture
async def world(sessions: async_sessionmaker[AsyncSession]) -> World:
    careers = FakeCareerOps()
    careers.script_discovery(
        "https://boards.greenhouse.io/acme", DiscoveryResult("greenhouse", "acme")
    )
    async with sessions() as session:
        conversation = await ConversationsRepo(session).create(now=NOW)
        message = await MessagesRepo(session).append(
            conversation.id, author="person", text="do it", now=NOW
        )
        await session.commit()
    return World(sessions, ActionServices(careers=careers), conversation.id, message.id)


async def company(world: World, name: str = "Acme", careers: str | None = None) -> UUID:
    async with world.sessions() as session:
        row = await CompaniesRepo(session).add(
            name=name, origin="user", resolution="unresolved", careers_url=careers
        )
        await session.commit()
        return row.id


async def applied_job(world: World) -> UUID:
    async with world.sessions() as session:
        acme = await CompaniesRepo(session).add(name="Acme", origin="user", resolution="verified")
        job = await JobsRepo(session).add(
            company_id=acme.id,
            company_name="Acme",
            title="Backend Engineer",
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="",
            state="applied",
            applied_on=date(2026, 11, 20),
        )
        await session.commit()
        return job.id


async def test_FR006_parity_companies(world: World) -> None:
    acme, zoho, globex = (
        await company(world),
        await company(world, "Zoho"),
        await company(world, "Globex"),
    )

    card, applied = await world.run(
        "hide_companies", companies=[f"company:{acme}", f"company:{zoho}"]
    )
    await world.run("delete_company", company=f"company:{globex}")

    assert card.card is not None
    assert card.card.summary == "Hide or show: Acme, Zoho"
    assert len(applied.results) == 2
    async with world.sessions() as session:
        rows = {r.name: r for r in await session.scalars(select(CompanyRow))}
    assert rows["Acme"].hidden
    assert rows["Zoho"].hidden
    assert "Globex" not in rows  # a company the person added is removed, as on the page


async def test_FR006_parity_board_choice(world: World) -> None:
    acme = await company(world, careers="https://boards.greenhouse.io/acme")
    other = await company(world, "Zoho", careers="https://boards.greenhouse.io/acme")

    await world.run("confirm_board", company=f"company:{acme}")
    await world.run("reject_board", company=f"company:{other}")

    async with world.sessions() as session:
        a = await session.get(CompanyRow, acme)
        b = await session.get(CompanyRow, other)
        assert a is not None
        assert b is not None
        assert (a.ats_vendor, a.board_id, a.resolution) == ("greenhouse", "acme", "user_confirmed")
        assert b.ats_vendor is None


async def test_FR006_parity_private_deletes(world: World) -> None:
    job_id = await applied_job(world)
    acme = await company(world)
    async with world.sessions() as session:
        contact = await ContactsRepo(session).add(
            acme, ContactFields(name="Zebulon Q", email="zeb@example.invalid"), source="typed"
        )
        repo = InterviewsRepo(session)
        round_row = await repo.add_round(job_id, kind="technical", interviewers="Ottoline")
        await repo.add_question(round_row.id, "secret-question-41", None)
        await repo.upsert_contact(job_id, ContactFields(name="Zebulon Q"))
        file = await ResumeFilesRepo(session).create(
            kind="upload_pdf", original_name="cv-file-55.pdf", size_bytes=5, sha256="e" * 64
        )
        await repo.set_resume(job_id, file.id, "cv-file-55.pdf", date(2026, 11, 20))
        await session.commit()
        question = (await session.scalars(select(InterviewQuestionRow))).one()

    await world.run("delete_contact", contact=f"contact:{contact.id}")
    await world.run("delete_question", question=f"question:{question.id}")
    await world.run("delete_round", round=f"round:{round_row.id}")
    await world.run("clear_interview_contact", job=f"job:{job_id}")
    await world.run("clear_resume_used", job=f"job:{job_id}")

    async with world.sessions() as session:
        assert (await session.scalars(select(ContactRow))).all() == []
        assert (await session.scalars(select(InterviewRoundRow))).all() == []
        details = await session.get(PipelineDetailsRow, job_id)
        assert details is None or (details.contact_name, details.resume_name) == (None, None)
