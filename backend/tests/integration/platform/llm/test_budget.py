"""T021: the budget guard blocks calls before the provider when the cap would be passed."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import FakeClock
from hiretitan.platform.llm.budget import BudgetGuard
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.port import AiUnavailable, LlmRequest, RenderedPrompt


class Answer(BaseModel):
    text: str


NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def request(user: str = "Summarize this resume.", max_out: int = 1000) -> LlmRequest[Answer]:
    return LlmRequest(
        task="extract_profile",
        prompt=RenderedPrompt("extract_profile", 1, "You extract profiles.", user),
        output_schema=Answer,
        tier="fast",
        max_output_tokens=max_out,
    )


def guard(sessions: async_sessionmaker[AsyncSession], inner: FakeLlm, cap: str) -> BudgetGuard:
    async def cap_provider() -> Decimal:
        return Decimal(cap)

    return BudgetGuard(
        inner,
        sessions=sessions,
        cap_provider=cap_provider,
        catalog=ModelCatalog.load(),
        provider="openai",
        clock=FakeClock(NOW),
    )


async def spend(sessions: async_sessionmaker[AsyncSession], amount: str) -> None:
    async with sessions() as session:
        await CallsRepo(session).record(
            LlmCallRecord(
                "t",
                "t",
                "1",
                "openai",
                "gpt-5.4-mini",
                0,
                0,
                0,
                Decimal(amount),
                Decimal(amount),
                0,
                "ok",
            ),
            created_at=NOW,
        )
        await session.commit()


async def rows(
    sessions: async_sessionmaker[AsyncSession],
) -> list[tuple[str, int, Decimal, Decimal]]:
    async with sessions() as session:
        result = await session.execute(
            text(
                "SELECT outcome, input_tokens, cost_usd, estimated_cost_usd"
                " FROM app.llm_calls WHERE outcome = 'budget_blocked'"
            )
        )
        return [tuple(r) for r in result.all()]  # type: ignore[misc]


async def test_FR032_call_blocked_before_provider_when_over_cap(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    inner = FakeLlm([Answer(text="x")])
    await spend(sessions, "24.999999")
    with pytest.raises(AiUnavailable) as blocked:
        await guard(sessions, inner, "25.00").generate(request())
    assert blocked.value.reason == "budget_reached"
    assert inner.calls == []  # the provider was never reached


async def test_FR032_blocked_call_logged(sessions: async_sessionmaker[AsyncSession]) -> None:
    await spend(sessions, "25")
    with pytest.raises(AiUnavailable):
        await guard(sessions, FakeLlm([Answer(text="x")]), "25.00").generate(request())
    [(outcome, tokens, cost, estimate)] = await rows(sessions)
    assert (outcome, tokens, cost) == ("budget_blocked", 0, Decimal(0))
    assert estimate > 0


async def test_under_cap_passes_through(sessions: async_sessionmaker[AsyncSession]) -> None:
    inner = FakeLlm([Answer(text="fine")])
    result = await guard(sessions, inner, "25.00").generate(request())
    assert result.value == Answer(text="fine")
    assert len(inner.calls) == 1
    assert await rows(sessions) == []


async def test_estimate_counts_input_and_max_output_tokens(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    # gpt-5.4-mini: $0.75 in / $4.50 out per 1M. 1M max output alone costs $4.50.
    with pytest.raises(AiUnavailable):
        await guard(sessions, FakeLlm([Answer(text="x")]), "4.00").generate(
            request(max_out=1_000_000)
        )
    [(_, _, _, estimate)] = await rows(sessions)
    assert Decimal("4.50") < estimate < Decimal("4.51")


async def test_last_month_spend_does_not_count(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        await CallsRepo(session).record(
            LlmCallRecord(
                "t", "t", "1", "openai", "m", 0, 0, 0, Decimal(100), Decimal(100), 0, "ok"
            ),
            created_at=datetime(2026, 10, 31, 23, 59, tzinfo=UTC),
        )
        await session.commit()
    inner = FakeLlm([Answer(text="ok")])
    assert (await guard(sessions, inner, "25.00").generate(request())).outcome == "ok"
