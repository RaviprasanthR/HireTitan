"""002m quick actions (FR-029, amended 2026-11-24): the chat's first way in.

Five actions with a small form each: a LinkedIn connection message, a LinkedIn message, an email,
a job's status, and adding a job. They run HireTitan's own actions; the chat itself makes no AI
call (a draft is written by the drafts workflow, as on the job's page).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.actions.cards import describe
from hiretitan.actions.registry import build_catalogue
from hiretitan.actions.spec import ActionServices
from hiretitan.api_main import create_app
from hiretitan.assistant.api.changes import create_changes_router
from hiretitan.assistant.api.conversations import create_conversations_router
from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.api.quick import create_quick_router
from hiretitan.assistant.application.ports import AssistantStatus
from hiretitan.assistant.application.turn import TurnDeps
from hiretitan.assistant.domain.quick import QUICK_ACTIONS
from hiretitan.assistant.infra.turn_store import SqlTurnStore
from hiretitan.assistant_wiring import CatalogAdapter, card_units, paste_into, undo_units
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
PROMPTS = Path(__file__).resolve().parents[3] / "src" / "hiretitan" / "prompts"


class NoClaims:
    async def unbacked(self, text: str, context: str) -> list[str]:
        return []


@dataclass
class Api:
    client: httpx.AsyncClient
    llm: FakeLlm
    sessions: async_sessionmaker[AsyncSession]

    async def messages(self, conversation: str) -> list[dict[str, Any]]:
        got = await self.client.get(f"/api/v1/assistant/conversations/{conversation}/messages")
        return list(got.json())

    async def conversation(self) -> str:
        return str((await self.client.post("/api/v1/assistant/conversations")).json()["id"])

    async def job(self, title: str, applied_on: date | None) -> UUID:
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
                state="applied" if applied_on else "explore",
                applied_on=applied_on,
            )
            await session.commit()
            return row.id


async def never_started(session: AsyncSession, mode: str, now: datetime) -> UUID:
    raise AssertionError("a card must wait for confirmation")


@pytest.fixture
async def api(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Api]:
    llm = FakeLlm()

    async def status() -> AssistantStatus:
        return AssistantStatus(False, "key_missing")  # quick actions work with no AI key

    async def describe_ref(text: str) -> dict[str, Any] | None:
        async with sessions() as session:
            card = await describe(session, text)
        return asdict(card) if card else None

    catalogue = build_catalogue()
    services = ActionServices(start_search=never_started)
    deps = AssistantApiDeps(
        sessions=sessions,
        turn=TurnDeps(
            llm=llm,
            catalog=CatalogAdapter(catalogue, sessions, services),
            store=SqlTurnStore(sessions),
            claims=NoClaims(),
            prompt=PromptRegistry(PROMPTS).load("mikasa_chat"),
            now=lambda: NOW,
        ),
        status=status,
        now=lambda: NOW,
        describe=describe_ref,
        cards=card_units(catalogue, sessions, lambda: NOW, services),
        undo=undo_units(catalogue, sessions, lambda: NOW, services),
        paste=paste_into(sessions, lambda: NOW),
    )
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_conversations_router(deps),
            create_quick_router(deps),
            create_changes_router(deps),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Api(client, llm, sessions)


async def test_FR029_the_five_quick_actions(api: Api) -> None:
    listed = (await api.client.get("/api/v1/assistant/quick-actions")).json()

    assert [(a["key"], a["form"]) for a in listed] == [
        ("linkedin_request", "draft"),
        ("linkedin_message", "draft"),
        ("email", "draft"),
        ("update_status", "status"),
        ("add_job", "paste"),
    ]
    assert [a["key"] for a in listed] == [a.key for a in QUICK_ACTIONS]
    assert listed[0]["label"] == "LinkedIn connection message"


async def test_FR029_status_marks_applied_with_undo_and_no_ai(api: Api) -> None:
    conversation = await api.conversation()
    job = await api.job("Backend Engineer", None)

    done = await api.client.post(
        f"/api/v1/assistant/conversations/{conversation}/quick/status",
        json={"job": f"job:{job}", "status": "applied"},
    )

    assert done.status_code == 200, done.text
    body = done.json()
    assert len(body["changes"]) == 1
    assert body["changes"][0]["undo_until"] is not None
    assert "applied" in body["text"].casefold()
    async with api.sessions() as session:
        row = await JobsRepo(session).get(job)
    assert row is not None
    assert row.state == "applied"
    said = await api.messages(conversation)
    assert [m["author"] for m in said] == ["person", "mikasa"]
    assert said[0]["text"] == "Update a job's status: applied"
    assert api.llm.calls == []
    assert api.llm.converse_calls == []


async def test_FR029_status_back_to_not_applied(api: Api) -> None:
    conversation = await api.conversation()
    job = await api.job("Backend Engineer", date(2026, 11, 20))

    done = await api.client.post(
        f"/api/v1/assistant/conversations/{conversation}/quick/status",
        json={"job": f"job:{job}", "status": "not_applied"},
    )

    assert done.status_code == 200, done.text
    async with api.sessions() as session:
        row = await JobsRepo(session).get(job)
    assert row is not None
    assert row.state != "applied"


async def test_FR029_status_checks_its_input(api: Api) -> None:
    conversation = await api.conversation()
    job = await api.job("Backend Engineer", None)
    url = f"/api/v1/assistant/conversations/{conversation}/quick/status"

    bad_status = await api.client.post(url, json={"job": f"job:{job}", "status": "hired"})
    bad_ref = await api.client.post(url, json={"job": "company:x", "status": "applied"})

    assert (bad_status.status_code, bad_ref.status_code) == (422, 422)
    assert await api.messages(conversation) == []


async def test_FR029_unknown_conversation(api: Api) -> None:
    missing = "0190a1b2-0000-7000-8000-0000000000aa"
    job = await api.job("Backend Engineer", None)

    status = await api.client.post(
        f"/api/v1/assistant/conversations/{missing}/quick/status",
        json={"job": f"job:{job}", "status": "applied"},
    )

    assert status.status_code == 404
