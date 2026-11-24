"""002m T013: Mikasa's API: status, conversations and the turn stream (contracts/rest-api.md;
FR-002, FR-021, FR-024, FR-028, EC-01, US4 scenario 2).

The real catalogue adapter and stores on Postgres; the scripted fake LLM.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.actions.cards import describe
from hiretitan.actions.registry import build_catalogue
from hiretitan.api_main import create_app
from hiretitan.assistant.api.conversations import create_conversations_router
from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.api.refs import create_refs_router
from hiretitan.assistant.api.status import create_status_router
from hiretitan.assistant.api.turns import create_turns_router
from hiretitan.assistant.application.ports import AssistantStatus
from hiretitan.assistant.application.turn import TurnDeps
from hiretitan.assistant.infra.repos import ConversationsRepo
from hiretitan.assistant.infra.turn_store import SqlTurnStore
from hiretitan.assistant_wiring import CatalogAdapter
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.port import TextDelta, ToolCall
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, JobsRepo

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
PROMPTS = Path(__file__).resolve().parents[3] / "src" / "hiretitan" / "prompts"


class NoClaims:
    async def unbacked(self, text: str, context: str) -> list[str]:
        return []


@dataclass
class Api:
    client: httpx.AsyncClient
    llm: FakeLlm
    status: list[AssistantStatus]


@pytest.fixture
async def api(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Api]:
    llm = FakeLlm()
    status = [AssistantStatus(True)]

    async def current_status() -> AssistantStatus:
        return status[0]

    async def describe_ref(text: str) -> dict[str, Any] | None:
        async with sessions() as session:
            card = await describe(session, text)
        return asdict(card) if card is not None else None

    deps = AssistantApiDeps(
        sessions=sessions,
        turn=TurnDeps(
            llm=llm,
            catalog=CatalogAdapter(build_catalogue(), sessions),
            store=SqlTurnStore(sessions),
            claims=NoClaims(),
            prompt=PromptRegistry(PROMPTS).load("mikasa_chat"),
            now=lambda: NOW,
        ),
        status=current_status,
        now=lambda: NOW,
        describe=describe_ref,
    )
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_status_router(deps),
            create_conversations_router(deps),
            create_turns_router(deps),
            create_refs_router(deps),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Api(client, llm, status)


def events(body: str) -> list[tuple[str, dict[str, Any]]]:
    found = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        lines = [line for line in block.split("\n") if line and not line.startswith(":")]
        name = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = "".join(line[6:] for line in lines if line.startswith("data: "))
        if name:
            found.append((name, json.loads(data)))
    return found


async def start(api: Api) -> str:
    created = await api.client.post("/api/v1/assistant/conversations")
    assert created.status_code == 201
    return str(created.json()["id"])


async def test_FR002_stream_events_in_order(
    api: Api, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        company = await CompaniesRepo(session).add(
            name="Acme", origin="user", resolution="verified"
        )
        job = await JobsRepo(session).add(
            company_id=company.id,
            company_name="Acme",
            title="Backend Engineer",
            first_seen_at=NOW,
            last_seen_at=NOW,
            description="",
            state="explore",
        )
        await session.commit()
    ref = f"job:{job.id}"
    api.llm.add_turn(TextDelta("Looking. "), ToolCall("c1", "search_jobs", "{}"))
    api.llm.add_turn(TextDelta(f"Found [[{ref}]]."))
    conversation = await start(api)

    response = await api.client.post(
        f"/api/v1/assistant/conversations/{conversation}/turns",
        json={"text": "What is in Explore?", "page": "/explore"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    found = events(response.text)
    assert [name for name, _ in found] == ["text", "text", "ref", "done"]
    assert found[2][1] == {"ref": ref}
    assert found[-1][1]["status"] == "complete"
    assert found[-1][1]["text"] == f"Looking. Found [[{ref}]]."

    history = await api.client.get(f"/api/v1/assistant/conversations/{conversation}/messages")
    assert [(m["author"], m["text"]) for m in history.json()] == [
        ("person", "What is in Explore?"),
        ("mikasa", f"Looking. Found [[{ref}]]."),
    ]
    listed = await api.client.get("/api/v1/assistant/conversations")
    assert listed.json()[0]["title"] == "What is in Explore?"


async def test_too_long_message_422(api: Api) -> None:
    conversation = await start(api)

    response = await api.client.post(
        f"/api/v1/assistant/conversations/{conversation}/turns", json={"text": "x" * 2001}
    )

    assert response.status_code == 422
    assert response.json()["reason"] == "too_long"


async def test_FR021_posting_like_message_refused(api: Api) -> None:
    conversation = await start(api)
    posting = (
        "About the role\n"
        + "Build things. " * 30
        + "\nResponsibilities\n"
        + "Design APIs. " * 20
        + "\nRequirements\n"
        + "Python. " * 20
    )

    response = await api.client.post(
        f"/api/v1/assistant/conversations/{conversation}/turns", json={"text": posting}
    )

    assert response.status_code == 422
    assert response.json()["reason"] == "looks_like_posting"
    assert api.llm.converse_calls == []  # never sent to the AI


async def test_EC01_turn_running_409(api: Api, sessions: async_sessionmaker[AsyncSession]) -> None:
    conversation = await start(api)
    async with sessions() as session:
        await ConversationsRepo(session).claim_turn(UUID(conversation), now=NOW)
        await session.commit()

    response = await api.client.post(
        f"/api/v1/assistant/conversations/{conversation}/turns", json={"text": "hello"}
    )

    assert response.status_code == 409
    assert response.json()["reason"] == "turn_running"


async def test_US4_AS2_key_missing_status(api: Api) -> None:
    api.status[0] = AssistantStatus(False, "key_missing")
    conversation = await start(api)

    status = await api.client.get("/api/v1/assistant/status")
    refused = await api.client.post(
        f"/api/v1/assistant/conversations/{conversation}/turns", json={"text": "hello"}
    )

    assert status.json() == {"available": False, "reason": "key_missing", "provider_message": None}
    assert refused.status_code == 503
    assert refused.json()["status_reason"] == "key_missing"


async def test_unknown_conversation_404(api: Api) -> None:
    missing = "0190a1b2-0000-7000-8000-0000000000aa"
    sent = await api.client.post(
        f"/api/v1/assistant/conversations/{missing}/turns", json={"text": "hi"}
    )
    listed = await api.client.get(f"/api/v1/assistant/conversations/{missing}/messages")
    assert (sent.status_code, listed.status_code) == (404, 404)


async def test_FR003_ref_card_for_the_person(
    api: Api, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        company = await CompaniesRepo(session).add(
            name="Acme", origin="user", resolution="verified"
        )
        contact = await ContactsRepo(session).add(
            company.id,
            ContactFields(name="Quillon Fairweather", role="Talent Partner"),
            source="typed",
        )
        await session.commit()

    found = await api.client.get(f"/api/v1/assistant/refs/contact:{contact.id}")
    gone = await api.client.get("/api/v1/assistant/refs/job:0190a1b2-0000-7000-8000-0000000000aa")
    bad = await api.client.get("/api/v1/assistant/refs/not-a-ref")

    assert found.status_code == 200
    assert found.json()["title"] == "Quillon Fairweather"  # private details go to the person
    assert found.json()["subtitle"] == "Talent Partner · Acme"
    assert (gone.status_code, bad.status_code) == (404, 404)
