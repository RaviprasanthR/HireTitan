"""T020: ``app.llm_calls`` and its repository (FR-012: every call is logged)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord


def record(**overrides: object) -> LlmCallRecord:
    values: dict[str, object] = {
        "task": "extract_profile",
        "prompt_name": "extract_profile",
        "prompt_version": "1",
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "input_tokens": 1000,
        "cached_input_tokens": 0,
        "output_tokens": 200,
        "cost_usd": Decimal("0.001650"),
        "estimated_cost_usd": Decimal("0.002000"),
        "latency_ms": 850,
        "outcome": "ok",
    }
    values.update(overrides)
    return LlmCallRecord(**values)  # type: ignore[arg-type]


async def test_FR012_every_call_logged(db_session: AsyncSession) -> None:
    repo = CallsRepo(db_session)
    await repo.record(record())
    await repo.record(
        record(outcome="budget_blocked", input_tokens=0, output_tokens=0, cost_usd=Decimal(0))
    )
    rows = (await db_session.execute(text("SELECT outcome FROM app.llm_calls ORDER BY id"))).all()
    assert [r.outcome for r in rows] == ["ok", "budget_blocked"]


async def test_no_prompt_or_response_text_is_stored(db_session: AsyncSession) -> None:
    columns = (
        (
            await db_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema = 'app' AND table_name = 'llm_calls'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert not {"prompt", "response", "text", "content", "output"} & set(columns)


async def test_monthly_spend_uses_utc_calendar_month(db_session: AsyncSession) -> None:
    repo = CallsRepo(db_session)
    at = lambda *args: datetime(*args, tzinfo=UTC)  # noqa: E731
    await repo.record(record(cost_usd=Decimal("1.5")), created_at=at(2026, 10, 31, 23, 59, 59))
    await repo.record(record(cost_usd=Decimal("2.0")), created_at=at(2026, 11, 1, 0, 0, 0))
    await repo.record(record(cost_usd=Decimal("0.25")), created_at=at(2026, 11, 30, 23, 59, 59))
    await repo.record(record(cost_usd=Decimal("4.0")), created_at=at(2026, 12, 1, 0, 0, 0))

    assert await repo.spent_in_month(2026, 11) == Decimal("2.25")
    assert await repo.spent_in_month(2026, 10) == Decimal("1.5")
    assert await repo.spent_in_month(2027, 1) == Decimal(0)


async def test_december_rolls_into_next_year(db_session: AsyncSession) -> None:
    repo = CallsRepo(db_session)
    await repo.record(
        record(cost_usd=Decimal("3")), created_at=datetime(2026, 12, 31, 23, 0, tzinfo=UTC)
    )
    await repo.record(record(cost_usd=Decimal("9")), created_at=datetime(2027, 1, 1, tzinfo=UTC))
    assert await repo.spent_in_month(2026, 12) == Decimal(3)


async def test_db_rejects_unknown_outcome(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await CallsRepo(db_session).record(record(outcome="great"))
