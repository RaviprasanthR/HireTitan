"""002m quick flow over HTTP: the staged routes map the flow's answers and refusals (FR-029)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
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
from hiretitan.assistant.api.staged import create_staged_router
from hiretitan.assistant.application.ports import (
    AssistantStatus,
    DraftRefusedError,
    StagedRefusedError,
    StagedView,
)
from hiretitan.assistant.application.turn import TurnDeps
from hiretitan.assistant.infra.turn_store import SqlTurnStore
from hiretitan.assistant_wiring import CatalogAdapter, card_units, paste_into, undo_units
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.prompts import PromptRegistry

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
PROMPTS = Path(__file__).resolve().parents[3] / "src" / "hiretitan" / "prompts"


class NoClaims:
    async def unbacked(self, text: str, context: str) -> list[str]:
        return []


@dataclass
class FakeFlow:
    """Records what the routes ask; answers with a canned view or the refusal set on it."""

    calls: list[tuple[str, Any]] = field(default_factory=list)
    refuse: Exception | None = None
    view_now: StagedView | None = None

    def _answer(self, step: str, kind: str | None = None) -> StagedView:
        if self.refuse:
            raise self.refuse
        return StagedView(step, kind, "Platform Engineer at Initech")  # type: ignore[arg-type]

    async def view(self, conversation_id: UUID) -> StagedView | None:
        return self.view_now

    async def begin(self, conversation_id: UUID, kind: str) -> StagedView:
        self.calls.append(("begin", kind))
        return self._answer("need_post", kind)

    async def hold_post(self, conversation_id: UUID, text: str) -> StagedView:
        self.calls.append(("post", text))
        return self._answer("need_kind")

    async def details(self, conversation_id: UUID, title: str, company: str) -> StagedView:
        self.calls.append(("details", (title, company)))
        return self._answer("need_kind")

    async def choose(self, conversation_id: UUID, kind: str) -> StagedView:
        self.calls.append(("choose", kind))
        return self._answer("drafting", kind)

    async def save(self, conversation_id: UUID) -> str:
        if self.refuse:
            raise self.refuse
        self.calls.append(("save", None))
        return "Saved Platform Engineer at Initech to your list."

    async def discard(self, conversation_id: UUID) -> None:
        self.calls.append(("discard", None))


@dataclass
class Api:
    client: httpx.AsyncClient
    flow: FakeFlow
    conversation: str


@pytest.fixture
async def api(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Api]:
    async def status() -> AssistantStatus:
        return AssistantStatus(True, None)

    async def describe_ref(text: str) -> dict[str, Any] | None:
        async with sessions() as session:
            card = await describe(session, text)
        return asdict(card) if card else None

    flow = FakeFlow()
    catalogue = build_catalogue()
    services = ActionServices()
    deps = AssistantApiDeps(
        sessions=sessions,
        turn=TurnDeps(
            llm=FakeLlm(),
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
        staged=flow,
    )
    app = create_app(
        Settings(),
        frontend_dist=tmp_path / "none",
        routers=[
            create_conversations_router(deps),
            create_changes_router(deps),
            create_staged_router(deps),
        ],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        conversation = (await client.post("/api/v1/assistant/conversations")).json()["id"]
        yield Api(client, flow, str(conversation))


def url(api: Api, tail: str = "") -> str:
    return f"/api/v1/assistant/conversations/{api.conversation}/staged{tail}"


async def test_nothing_held_is_null(api: Api) -> None:
    got = await api.client.get(url(api))

    assert got.status_code == 200
    assert got.json() is None


async def test_a_held_post_is_described(api: Api) -> None:
    api.flow.view_now = StagedView(
        "ask_save", "email", "Platform Engineer at Initech", "job:j", "draft:d"
    )

    body = (await api.client.get(url(api))).json()

    assert body == {
        "step": "ask_save",
        "kind": "email",
        "label": "Platform Engineer at Initech",
        "job_ref": "job:j",
        "draft_ref": "draft:d",
        "already_saved": False,
    }


async def test_begin_post_details_choose_save_discard_reach_the_flow(api: Api) -> None:
    assert (await api.client.post(url(api, "/begin"), json={"kind": "email"})).status_code == 200
    assert (
        await api.client.post(url(api, "/post"), json={"text": "Job post here"})
    ).status_code == 200
    details = await api.client.post(
        url(api, "/details"), json={"title": "Platform Engineer", "company": "Initech"}
    )
    assert details.status_code == 200
    chosen = await api.client.post(url(api, "/choose"), json={"kind": "referral_message"})
    assert chosen.json()["step"] == "drafting"
    saved = await api.client.post(url(api, "/save"))
    assert saved.json() == {"summary": "Saved Platform Engineer at Initech to your list."}
    assert (await api.client.post(url(api, "/discard"))).status_code == 204

    assert [name for name, _ in api.flow.calls] == [
        "begin",
        "post",
        "details",
        "choose",
        "save",
        "discard",
    ]


async def test_a_kind_must_be_one_of_the_three(api: Api) -> None:
    refused = await api.client.post(url(api, "/begin"), json={"kind": "tweet"})

    assert refused.status_code == 422
    assert api.flow.calls == []


async def test_a_refused_step_says_why(api: Api) -> None:
    api.flow.refuse = StagedRefusedError("Paste a job post first.")

    refused = await api.client.post(url(api, "/choose"), json={"kind": "email"})

    assert refused.status_code == 422
    assert refused.json()["detail"] == "Paste a job post first."


async def test_a_draft_that_cannot_start_is_a_conflict_with_the_reason(api: Api) -> None:
    api.flow.refuse = DraftRefusedError("Finish your profile first, then write a draft.")

    refused = await api.client.post(url(api, "/choose"), json={"kind": "email"})

    assert refused.status_code == 409
    assert "Finish your profile first" in refused.json()["detail"]


async def test_an_unknown_conversation_is_not_found(api: Api) -> None:
    missing = "/api/v1/assistant/conversations/0190a1b2-0000-7000-8000-0000000000aa/staged"

    got = await api.client.get(missing)
    posted = await api.client.post(f"{missing}/post", json={"text": "x"})

    assert (got.status_code, posted.status_code) == (404, 404)
    assert api.flow.calls == []
