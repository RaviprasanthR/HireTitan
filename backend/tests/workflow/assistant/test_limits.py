"""002m T034 (US4): Mikasa's limits are clear. The status says why she cannot answer, a decline
keeps its Settings link, and a failed turn leaves the conversation usable.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.workflow.assistant.test_turn import (
    JOBS_ANSWER,
    FakeCatalog,
    conversation,
    deps,
    done,
    messages,
    turn,
)

from hiretitan.assistant.application.turn import ErrorEvent
from hiretitan.assistant_wiring import StatusCheck
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.port import AiUnavailable, TextDelta, ToolCall

TOOLS = ModelCatalog(
    tiers={"fake": {"fast": "m"}}, capabilities={"fake": {"m": frozenset({"tools"})}}
)
NO_TOOLS = ModelCatalog(tiers={"fake": {"fast": "m"}}, capabilities={"fake": {"m": frozenset()}})


def check(
    sessions: async_sessionmaker[AsyncSession], *, catalog: ModelCatalog = TOOLS, key: bool = True
) -> StatusCheck:
    return StatusCheck(sessions, provider="fake", has_key=lambda: key, catalog=catalog)


async def test_US4_AS1_declines_with_link(sessions: async_sessionmaker[AsyncSession]) -> None:
    llm = FakeLlm()
    llm.add_turn(ToolCall("c1", "search_jobs", '{"list": "pipeline"}'))
    llm.add_turn(TextDelta("I can't delete your data. You can do it in [[page:/settings]]."))
    d = deps(sessions, llm, FakeCatalog({"search_jobs": JOBS_ANSWER}))

    events = await turn(d, await conversation(sessions), "Delete all my data")

    assert "[[page:/settings]]" in done(events).text  # R9's link check keeps a real page


async def test_US4_AS3_model_lacks_tools(sessions: async_sessionmaker[AsyncSession]) -> None:
    found = await check(sessions, catalog=NO_TOOLS)()
    assert (found.available, found.reason) == (False, "model_lacks_tools")


async def test_US4_status_reasons(sessions: async_sessionmaker[AsyncSession]) -> None:
    assert (await check(sessions, key=False)()).reason == "key_missing"
    assert (await check(sessions)()).available is True
    for status, reason, message in (
        ("rejected", "key_rejected", None),
        ("out_of_credit", "out_of_credit", "You exceeded your quota"),
    ):
        async with sessions() as session:
            await ProviderStatusRepo(session).set("fake", status, message)
            await session.commit()
        found = await check(sessions)()
        assert (found.available, found.reason, found.provider_message) == (False, reason, message)


async def test_US4_AS2_out_of_credit_keeps_conversation(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    llm = FakeLlm()
    llm.add_turn(AiUnavailable("out_of_credit", "You exceeded your quota"))
    llm.add_turn(AiUnavailable("key_rejected"))
    d = deps(sessions, llm)
    conv = await conversation(sessions)

    first = await turn(d, conv, "hi")
    assert next(e for e in first if isinstance(e, ErrorEvent)).provider_message
    second = await turn(d, conv, "hello again")  # the conversation is free and kept

    error = next(e for e in second if isinstance(e, ErrorEvent))
    assert "rejected" in error.message
    stored = await messages(sessions, conv)
    assert [m.author for m in stored] == ["person", "mikasa", "person", "mikasa"]
