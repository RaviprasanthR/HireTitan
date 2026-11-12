"""T020: ``app.llm_calls`` and its repository (FR-012: every call is logged)."""

from __future__ import annotations

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
        "latency_ms": 850,
        "outcome": "ok",
    }
    values.update(overrides)
    return LlmCallRecord(**values)  # type: ignore[arg-type]


async def test_FR012_every_call_logged(db_session: AsyncSession) -> None:
    repo = CallsRepo(db_session)
    await repo.record(record())
    await repo.record(record(outcome="error", input_tokens=0, output_tokens=0))
    rows = (await db_session.execute(text("SELECT outcome FROM app.llm_calls ORDER BY id"))).all()
    assert [r.outcome for r in rows] == ["ok", "error"]


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


async def test_FR013_calls_are_logged_without_cost(db_session: AsyncSession) -> None:
    await CallsRepo(db_session).record(record())

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
    assert not [c for c in columns if "cost" in c or "price" in c]
    assert {"input_tokens", "cached_input_tokens", "output_tokens"} <= set(columns)  # tokens stay


async def test_db_rejects_unknown_outcome(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await CallsRepo(db_session).record(record(outcome="great"))
