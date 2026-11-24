"""002m T012: one chat turn with Mikasa, read-only (US1; FR-002, FR-018a, FR-023, FR-024, FR-025,
EC-01, EC-09, SC-005, SC-008; research R9).

Real Postgres for the stored conversation and the call log; the scripted fake LLM; a small fake
catalogue and profile check so each rule is tested on its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.assistant.application.ports import CallContext, ToolOutcome
from hiretitan.assistant.application.turn import (
    REFUSED_TEXT,
    UNBACKED_TEXT,
    DoneEvent,
    ErrorEvent,
    LooksLikePostingError,
    MessageTooLongError,
    NoticeEvent,
    RefEvent,
    TextEvent,
    TurnDeps,
    TurnEvent,
    TurnRunningError,
    begin,
    run_turn,
)
from hiretitan.assistant.infra.models import ConversationRow, MessageRow
from hiretitan.assistant.infra.repos import ConversationsRepo
from hiretitan.assistant.infra.turn_store import SqlTurnStore
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.infra.models import LlmCallRow
from hiretitan.platform.llm.port import AiUnavailable, TextDelta, ToolCall, ToolSpec
from hiretitan.platform.llm.prompts import PromptRegistry

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
PROMPTS = Path(__file__).resolve().parents[3] / "src" / "hiretitan" / "prompts"
JOB = "job:0190a1b2-0000-7000-8000-000000000001"
OTHER = "job:0190a1b2-0000-7000-8000-0000000000ff"


@dataclass
class FakeCatalog:
    """Answers tool calls from a dict; records what it was asked."""

    answers: dict[str, ToolOutcome] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def tool_specs(self) -> list[ToolSpec]:
        return [ToolSpec(name, "", {"type": "object"}) for name in self.answers]

    async def call(self, name: str, arguments_json: str, ctx: CallContext) -> ToolOutcome:
        self.calls.append((name, arguments_json))
        return self.answers.get(
            name, ToolOutcome(kind="unknown", valid=False, problem=f"there is no tool {name}")
        )


@dataclass
class FakeClaims:
    """Treats any listed word as unbacked by the profile."""

    unbacked_words: tuple[str, ...] = ()
    checked: list[str] = field(default_factory=list)

    async def unbacked(self, text: str, context: str) -> list[str]:
        self.checked.append(text)
        return [w for w in self.unbacked_words if w in text]


JOBS_ANSWER = ToolOutcome(
    kind="read",
    valid=True,
    payload={"items": [{"ref": JOB, "title": "Backend Engineer"}], "total": 1},
    refs=[JOB],
)


def deps(
    sessions: async_sessionmaker[AsyncSession],
    llm: FakeLlm,
    catalog: FakeCatalog | None = None,
    claims: FakeClaims | None = None,
    **extra: Any,
) -> TurnDeps:
    return TurnDeps(
        llm=llm,
        catalog=catalog or FakeCatalog({"search_jobs": JOBS_ANSWER}),
        store=SqlTurnStore(sessions),
        claims=claims or FakeClaims(),
        prompt=PromptRegistry(PROMPTS).load("mikasa_chat"),
        now=lambda: NOW,
        **extra,
    )


async def conversation(sessions: async_sessionmaker[AsyncSession]) -> UUID:
    async with sessions() as session:
        row = await ConversationsRepo(session).create(now=NOW)
        await session.commit()
        return row.id


async def turn(d: TurnDeps, conv: UUID, text: str) -> list[TurnEvent]:
    message_id = await begin(d, conv, text)
    return [event async for event in run_turn(d, conv, page="/companies", message_id=message_id)]


async def messages(sessions: async_sessionmaker[AsyncSession], conv: UUID) -> list[MessageRow]:
    async with sessions() as session:
        rows = await session.scalars(
            select(MessageRow).where(MessageRow.conversation_id == conv).order_by(MessageRow.seq)
        )
        return list(rows)


def done(events: list[TurnEvent]) -> DoneEvent:
    last = events[-1]
    assert isinstance(last, DoneEvent)
    return last


async def test_US1_AS2_answers_from_read_actions(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    llm = FakeLlm()
    llm.add_turn(ToolCall("c1", "search_jobs", '{"list": "pipeline"}'))
    llm.add_turn(TextDelta("You applied to "), TextDelta(f"[[{JOB}]]."))
    catalog = FakeCatalog({"search_jobs": JOBS_ANSWER})
    d = deps(sessions, llm, catalog)
    conv = await conversation(sessions)

    events = await turn(d, conv, "What did I apply to this week?")

    assert [e.delta for e in events if isinstance(e, TextEvent)] == [
        "You applied to ",
        f"[[{JOB}]].",
    ]
    assert RefEvent(JOB) in events
    assert done(events).text == f"You applied to [[{JOB}]]."
    assert catalog.calls == [("search_jobs", '{"list": "pipeline"}')]
    # the second round saw the result as a data block after the call
    second = llm.converse_calls[1].messages
    assert second[-2].role == "tool_call"
    assert second[-1].role == "tool_result"
    assert second[-1].text.startswith("<<DATA ")
    assert json.loads(second[-1].text.splitlines()[1]) == JOBS_ANSWER.payload
    # the first entry tells the model today's date and the open page
    assert second[0].role == "note"
    assert "2026-11-24" in second[0].text
    assert "/companies" in second[0].text
    stored = await messages(sessions, conv)
    assert [(m.author, m.status) for m in stored] == [
        ("person", "complete"),
        ("mikasa", "complete"),
    ]
    assert stored[1].refs == [JOB]


async def test_US1_AS3_no_data_says_so(sessions: async_sessionmaker[AsyncSession]) -> None:
    llm = FakeLlm()
    empty = ToolOutcome(kind="read", valid=True, payload={"items": [], "total": 0})
    llm.add_turn(ToolCall("c1", "search_companies", '{"name": "Globex"}'))
    llm.add_turn(TextDelta("I don't have Globex in HireTitan."))
    d = deps(sessions, llm, FakeCatalog({"search_companies": empty}))

    events = await turn(d, await conversation(sessions), "What does Globex pay?")

    assert done(events).text == "I don't have Globex in HireTitan."


async def test_US1_AS6_read_changes_nothing(sessions: async_sessionmaker[AsyncSession]) -> None:
    llm = FakeLlm()
    llm.add_turn(ToolCall("c1", "search_jobs", "{}"))
    llm.add_turn(TextDelta("Done."))
    conv = await conversation(sessions)

    await turn(deps(sessions, llm), conv, "List my jobs")

    stored = await messages(sessions, conv)
    assert stored[1].tool_trace == [
        {"tool": "search_jobs", "kind": "read", "valid": True, "refs": [JOB]}
    ]


async def test_FR023_each_round_logged(sessions: async_sessionmaker[AsyncSession]) -> None:
    llm = FakeLlm()
    llm.add_turn(ToolCall("c1", "search_jobs", "{}"))
    llm.add_turn(TextDelta("Two jobs."))

    await turn(deps(sessions, llm), await conversation(sessions), "List my jobs")

    async with sessions() as session:
        rows = list(await session.scalars(select(LlmCallRow).order_by(LlmCallRow.created_at)))
    assert [(r.task, r.prompt_name, r.prompt_version, r.outcome) for r in rows] == [
        ("mikasa_turn", "mikasa_chat", "1", "ok"),
        ("mikasa_turn", "mikasa_chat", "1", "ok"),
    ]


async def test_FR025_unknown_tool_repaired_once_then_refused(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    llm = FakeLlm()
    llm.add_turn(ToolCall("c1", "delete_everything", "{}"))  # unknown: repaired once
    llm.add_turn(ToolCall("c2", "search_jobs", "{}"))
    llm.add_turn(TextDelta("Found one."))
    d = deps(sessions, llm)

    repaired = await turn(d, await conversation(sessions), "List my jobs")

    assert done(repaired).text == "Found one."
    problem = llm.converse_calls[1].messages[-1]
    assert problem.role == "tool_result"
    assert "not valid" in problem.text

    llm.add_turn(ToolCall("c3", "delete_everything", "{}"))
    llm.add_turn(ToolCall("c4", "delete_everything", "{}"))  # second invalid call: refused
    conv = await conversation(sessions)
    refused = await turn(d, conv, "Delete everything")

    assert done(refused).text == REFUSED_TEXT
    stored = await messages(sessions, conv)
    assert stored[-1].tool_trace[-1] == {"outcome": "refused"}


async def test_EC09_malformed_call_never_reaches_an_action(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    llm = FakeLlm()
    llm.add_turn(ToolCall("c1", "nope", "{}"))
    llm.add_turn(ToolCall("c2", "nope", "{}"))
    catalog = FakeCatalog({"search_jobs": JOBS_ANSWER})

    await turn(deps(sessions, llm, catalog), await conversation(sessions), "do it")

    assert [name for name, _ in catalog.calls] == ["nope", "nope"]  # refused by the catalogue


async def test_R9_unknown_ref_removed(sessions: async_sessionmaker[AsyncSession]) -> None:
    llm = FakeLlm()
    llm.add_turn(ToolCall("c1", "search_jobs", "{}"))
    llm.add_turn(TextDelta(f"See [[{JOB}]] and [[{OTHER}]] or [[page:/admin]]."))

    events = await turn(deps(sessions, llm), await conversation(sessions), "List")

    assert done(events).text == f"See [[{JOB}]] and or."
    assert RefEvent(OTHER) not in events


async def test_EC01_second_turn_refused_while_running(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    d = deps(sessions, FakeLlm())
    conv = await conversation(sessions)
    await begin(d, conv, "first")

    with pytest.raises(TurnRunningError):
        await begin(d, conv, "second")
    assert len(await messages(sessions, conv)) == 1


async def test_FR021_long_and_posting_messages_refused(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    d = deps(sessions, FakeLlm())
    conv = await conversation(sessions)
    posting = (
        "About the role\n"
        + "Build things. " * 30
        + "\nResponsibilities\n"
        + "Design APIs. " * 20
        + "\nRequirements\n"
        + "Python. " * 20
    )

    with pytest.raises(MessageTooLongError):
        await begin(d, conv, "x" * 2001)
    with pytest.raises(LooksLikePostingError):
        await begin(d, conv, posting)
    assert await messages(sessions, conv) == []
    async with sessions() as session:
        row = await session.get(ConversationRow, conv)
        assert row is not None
        assert row.turn_running is False


async def test_FR002_stop_saves_partial_reply(sessions: async_sessionmaker[AsyncSession]) -> None:
    llm = FakeLlm()
    llm.add_turn(ToolCall("c1", "search_jobs", "{}"))
    llm.add_turn(TextDelta("Here is "), TextDelta("a long answer"), TextDelta(" never seen"))
    d = deps(sessions, llm)
    conv = await conversation(sessions)
    await begin(d, conv, "Tell me everything")

    stream = run_turn(d, conv, page="/")
    first = await anext(stream)
    second = await anext(stream)
    await stream.aclose()  # the person pressed Stop

    assert (first, second) == (TextEvent("Here is "), TextEvent("a long answer"))
    stored = await messages(sessions, conv)
    assert (stored[-1].author, stored[-1].status, stored[-1].text) == (
        "mikasa",
        "stopped",
        "Here is a long answer",
    )
    async with sessions() as session:
        row = await session.get(ConversationRow, conv)
        assert row is not None
        assert row.turn_running is False  # free for the next message


async def test_FR024_out_of_credit_turn_failed_with_message(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    llm = FakeLlm()
    llm.add_turn(AiUnavailable("out_of_credit", "You exceeded your current quota"))
    conv = await conversation(sessions)

    events = await turn(deps(sessions, llm), conv, "hi")

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.reason == "ai_unavailable"
    assert error.provider_message == "You exceeded your current quota"
    assert done(events).status == "failed"
    stored = await messages(sessions, conv)
    assert stored[-1].status == "failed"
    assert stored[-1].error == {
        "reason": "out_of_credit",
        "provider_message": "You exceeded your current quota",
    }


async def test_SC008_unavailable_or_invalid_ends_with_reason_and_no_change(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    for script in (
        [AiUnavailable("key_missing")],
        [ToolCall("a", "nope", "{}"), ToolCall("b", "nope", "{}")],
    ):
        llm = FakeLlm()
        for step in script:
            llm.add_turn(step)
        catalog = FakeCatalog({"search_jobs": JOBS_ANSWER})
        events = await turn(deps(sessions, llm, catalog), await conversation(sessions), "go")
        assert isinstance(events[-1], DoneEvent)
        assert events[-1].text or any(isinstance(e, ErrorEvent) for e in events)
        assert all(name != "search_jobs" for name, _ in catalog.calls)  # nothing was run


async def test_FR018a_unbacked_claim_repaired_then_replaced(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    profile = ToolOutcome(kind="read", valid=True, payload={"items": [{"skills": ["Python"]}]})
    catalog = FakeCatalog({"get_profile": profile})
    claims = FakeClaims(unbacked_words=("Rust",))

    llm = FakeLlm()
    llm.add_turn(TextDelta("Let me look. "), ToolCall("c1", "get_profile", "{}"))
    llm.add_turn(TextDelta("You know Python and Rust."))
    llm.add_turn(TextDelta("You know Python."))  # the rewrite passes
    events = await turn(deps(sessions, llm, catalog, claims), await conversation(sessions), "?")

    assert done(events).text == "You know Python."
    assert NoticeEvent("checking_profile", "Checking against your profile…") in events
    # nothing held for the check was streamed
    assert [e.delta for e in events if isinstance(e, TextEvent)] == []
    assert llm.converse_calls[-1].tools == []  # the rewrite round gets no tools
    assert llm.converse_calls[-1].messages[-1].role == "note"

    llm.add_turn(ToolCall("c2", "get_profile", "{}"))
    llm.add_turn(TextDelta("You know Rust."))
    llm.add_turn(TextDelta("You really know Rust."))  # the rewrite fails too
    events = await turn(deps(sessions, llm, catalog, claims), await conversation(sessions), "?")

    assert done(events).text == UNBACKED_TEXT


async def test_SC005_seeded_unbacked_claims_all_rejected(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    profile = ToolOutcome(kind="read", valid=True, payload={"items": [{}]})
    seeded = ("led 40 engineers", "Kubernetes", "at Globex", "since 2009")
    for claim in seeded:
        llm = FakeLlm()
        llm.add_turn(ToolCall("c", "get_profile", "{}"))
        llm.add_turn(TextDelta(f"You {claim}."))
        llm.add_turn(TextDelta(f"Again, you {claim}."))
        claims = FakeClaims(unbacked_words=(claim,))
        events = await turn(
            deps(sessions, llm, FakeCatalog({"get_profile": profile}), claims),
            await conversation(sessions),
            "Tell me about my experience",
        )
        assert claim not in done(events).text


async def test_SC008_unexpected_failure_ends_with_reason(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    class BrokenCatalog(FakeCatalog):
        async def call(self, name: str, arguments_json: str, ctx: CallContext) -> ToolOutcome:
            raise RuntimeError("database went away")

    llm = FakeLlm()
    llm.add_turn(TextDelta("Looking. "), ToolCall("c1", "search_jobs", "{}"))
    conv = await conversation(sessions)

    events = await turn(deps(sessions, llm, BrokenCatalog()), conv, "List my jobs")

    error = next(e for e in events if isinstance(e, ErrorEvent))
    assert error.reason == "internal"
    assert done(events).status == "failed"
    stored = await messages(sessions, conv)
    # text held for a first action is not shown or kept (FR-031)
    assert (stored[-1].status, stored[-1].text) == ("failed", "")
    async with sessions() as session:
        row = await session.get(ConversationRow, conv)
        assert row is not None
        assert row.turn_running is False
