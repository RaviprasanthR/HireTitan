"""002m T028: changes and cards through the turn and the API (FR-004, FR-010 to FR-015, FR-021,
US2 scenarios 6 and 7, SC-010; contracts/rest-api.md)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.actions.cards import describe
from hiretitan.actions.registry import build_catalogue
from hiretitan.api_main import create_app
from hiretitan.assistant.api.changes import create_changes_router
from hiretitan.assistant.api.conversations import create_conversations_router
from hiretitan.assistant.api.deps import AssistantApiDeps
from hiretitan.assistant.api.turns import create_turns_router
from hiretitan.assistant.application.ports import AssistantStatus
from hiretitan.assistant.application.turn import TurnDeps
from hiretitan.assistant.infra.turn_store import SqlTurnStore
from hiretitan.assistant_wiring import CatalogAdapter, card_units, paste_into, undo_units
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.port import TextDelta, ToolCall
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.search.infra.models import JobRow
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
    published: list[list[list[str]]] = field(default_factory=list)

    async def conversation(self) -> str:
        return str((await self.client.post("/api/v1/assistant/conversations")).json()["id"])

    async def turn(self, conversation: str, text: str) -> list[tuple[str, dict[str, Any]]]:
        response = await self.client.post(
            f"/api/v1/assistant/conversations/{conversation}/turns", json={"text": text}
        )
        assert response.status_code == 200, response.text
        found = []
        for block in response.text.replace("\r\n", "\n").split("\n\n"):
            lines = [line for line in block.split("\n") if line and not line.startswith(":")]
            name = next((line[7:] for line in lines if line.startswith("event: ")), None)
            data = "".join(line[6:] for line in lines if line.startswith("data: "))
            if name:
                found.append((name, json.loads(data)))
        return found

    async def job(self, title: str = "Backend Engineer", state: str = "explore") -> UUID:
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
            await session.commit()
            return row.id

    async def state(self, job_id: UUID) -> str | None:
        async with self.sessions() as session:
            row = await session.get(JobRow, job_id)
            return row.state if row else None


@pytest.fixture
async def api(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Api]:
    llm = FakeLlm()
    holder: list[Api] = []

    async def status() -> AssistantStatus:
        return AssistantStatus(True)

    async def publish(keys: list[list[str]]) -> None:
        holder[0].published.append(keys)

    async def describe_ref(text: str) -> dict[str, Any] | None:
        async with sessions() as session:
            card = await describe(session, text)
        return asdict(card) if card else None

    catalogue = build_catalogue()
    deps = AssistantApiDeps(
        sessions=sessions,
        turn=TurnDeps(
            llm=llm,
            catalog=CatalogAdapter(catalogue, sessions),
            store=SqlTurnStore(sessions),
            claims=NoClaims(),
            prompt=PromptRegistry(PROMPTS).load("mikasa_chat"),
            now=lambda: NOW,
            publish=publish,
        ),
        status=status,
        now=lambda: NOW,
        describe=describe_ref,
        cards=card_units(catalogue, sessions, lambda: NOW),
        undo=undo_units(catalogue, sessions, lambda: NOW),
        paste=paste_into(sessions, lambda: NOW),
        publish=publish,
    )
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_conversations_router(deps),
            create_turns_router(deps),
            create_changes_router(deps),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        holder.append(Api(client, llm, sessions))
        yield holder[0]


async def test_US2_AS1_small_change_streams_with_undo_and_tells_tabs(api: Api) -> None:
    job_id = await api.job()
    api.llm.add_turn(ToolCall("c1", "mark_applied", json.dumps({"job": f"job:{job_id}"})))
    api.llm.add_turn(TextDelta("Marked."))
    conversation = await api.conversation()

    events = await api.turn(conversation, "I applied to the Acme job")

    change = next(data for name, data in events if name == "change")
    assert change["summary"] == "Marked Backend Engineer at Acme as applied on 2026-11-24."
    assert change["undo_until"]
    assert await api.state(job_id) == "applied"
    assert api.published[0] == [["jobs"], ["pipeline"], ["search-latest"]]  # FR-004

    undone = await api.client.post(f"/api/v1/assistant/changes/{change['change_id']}/undo")
    again = await api.client.post(f"/api/v1/assistant/changes/{change['change_id']}/undo")

    assert undone.status_code == 200
    assert (again.status_code, again.json()["reason"]) == (409, "already_undone")
    assert await api.state(job_id) == "explore"
    history = (
        await api.client.get(f"/api/v1/assistant/conversations/{conversation}/messages")
    ).json()
    assert history[0]["changes"][0]["undone"] is True
    # the history keeps what the change did, so the notice reads the same after a reload
    assert history[0]["changes"][0]["summary"] == change["summary"]


async def test_US2_AS4_card_confirm_and_cancel_through_the_api(api: Api) -> None:
    first, second = await api.job(), await api.job("Data Engineer")
    for job_id in (first, second):
        api.llm.add_turn(ToolCall("c", "delete_job", json.dumps({"job": f"job:{job_id}"})))
        api.llm.add_turn(TextDelta("Confirm to delete it."))
    conversation = await api.conversation()

    cards = []
    for _ in (first, second):
        events = await api.turn(conversation, "Delete that job")
        cards.append(next(data for name, data in events if name == "card"))
    assert await api.state(first) == "explore"  # nothing changed before confirming

    confirmed = await api.client.post(f"/api/v1/assistant/cards/{cards[0]['card_id']}/confirm")
    cancelled = await api.client.post(f"/api/v1/assistant/cards/{cards[1]['card_id']}/cancel")
    twice = await api.client.post(f"/api/v1/assistant/cards/{cards[0]['card_id']}/confirm")

    assert confirmed.status_code == 200
    assert confirmed.json()["results"][0]["summary"] == "Deleted Backend Engineer at Acme."
    assert cancelled.json()["state"] == "cancelled"
    assert (twice.status_code, twice.json()["reason"]) == (409, "not_proposed")
    assert (await api.state(first), await api.state(second)) == ("deleted", "explore")
    history = (
        await api.client.get(f"/api/v1/assistant/conversations/{conversation}/messages")
    ).json()
    states = [card["state"] for message in history for card in message["cards"]]
    assert states == ["applied", "cancelled"]


async def test_US2_AS7_failed_change_reports_reason(api: Api) -> None:
    job_id = await api.job(state="applied")
    api.llm.add_turn(ToolCall("c1", "mark_applied", json.dumps({"job": f"job:{job_id}"})))
    api.llm.add_turn(TextDelta("You had already marked it."))
    conversation = await api.conversation()

    events = await api.turn(conversation, "I applied to it")

    assert not any(name == "change" for name, _ in events)
    result = api.llm.converse_calls[1].messages[-1]
    assert "already_applied" in result.text  # the model gets the plain reason to pass on


async def test_FR013_two_matches_asks_which(api: Api) -> None:
    await api.job("Backend Engineer")
    await api.job("Backend Engineer II")
    api.llm.add_turn(ToolCall("c1", "search_jobs", json.dumps({"company": "Acme"})))
    api.llm.add_turn(TextDelta("There are two Acme jobs. Which one?"))
    conversation = await api.conversation()

    events = await api.turn(conversation, "Mark the Acme job applied")

    assert not any(name in ("change", "card") for name, _ in events)
    async with api.sessions() as session:
        assert {r.state for r in await session.scalars(select(JobRow))} == {"explore"}


async def test_FR021_paste_text_never_sent(api: Api) -> None:
    conversation = await api.conversation()
    description = "We build things. paste-distinctive-8842 " * 5

    pasted = await api.client.post(
        f"/api/v1/assistant/conversations/{conversation}/paste",
        json={
            "url": "https://jobs.example.com/acme/77",
            "description": description,
            "title": "Backend Engineer",
            "company": "Acme",
        },
    )
    api.llm.add_turn(TextDelta("Got it."))
    await api.turn(conversation, "Thanks")

    assert pasted.status_code == 201
    assert pasted.json()["summary"] == "Added Backend Engineer at Acme."
    sent = json.dumps([m.text for c in api.llm.converse_calls for m in c.messages])
    assert "paste-distinctive-8842" not in sent
    undone = await api.client.post(f"/api/v1/assistant/changes/{pasted.json()['change_id']}/undo")
    assert undone.status_code == 200
    async with api.sessions() as session:
        assert (await session.scalars(select(JobRow))).all() == []


async def test_SC010_private_change_actions_never_echo_values(api: Api) -> None:
    async with api.sessions() as session:
        company = await CompaniesRepo(session).add(
            name="Acme", origin="user", resolution="verified"
        )
        await session.commit()
    api.llm.add_turn(
        ToolCall(
            "c1",
            "add_contact",
            json.dumps(
                {"company": f"company:{company.id}", "name": "Zebulon Q", "phone": "+1 555 0177"}
            ),
        )
    )
    api.llm.add_turn(
        ToolCall("c2", "list_contacts", json.dumps({"company": f"company:{company.id}"}))
    )
    api.llm.add_turn(TextDelta("Saved."))
    conversation = await api.conversation()

    await api.turn(conversation, "Add Zebulon Q, +1 555 0177, as my Acme contact")

    results = [
        m.text for c in api.llm.converse_calls for m in c.messages if m.role == "tool_result"
    ]
    assert results
    for text in results:
        assert "Zebulon" not in text
        assert "555 0177" not in text
