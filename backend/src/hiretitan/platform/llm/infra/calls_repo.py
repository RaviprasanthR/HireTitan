"""Repository for the LLM call log and the monthly spend (FR-012, FR-032)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.llm.infra.models import LlmCallRow


@dataclass(frozen=True, slots=True)
class LlmCallRecord:
    task: str
    prompt_name: str
    prompt_version: str
    provider: str
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    estimated_cost_usd: Decimal
    latency_ms: int
    outcome: str
    run_id: UUID | None = None


class CallsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, call: LlmCallRecord, *, created_at: datetime | None = None) -> None:
        row = LlmCallRow(
            run_id=call.run_id,
            task=call.task,
            prompt_name=call.prompt_name,
            prompt_version=call.prompt_version,
            provider=call.provider,
            model=call.model,
            input_tokens=call.input_tokens,
            cached_input_tokens=call.cached_input_tokens,
            output_tokens=call.output_tokens,
            cost_usd=call.cost_usd,
            estimated_cost_usd=call.estimated_cost_usd,
            latency_ms=call.latency_ms,
            outcome=call.outcome,
        )
        if created_at is not None:
            row.created_at = created_at
        self._session.add(row)
        await self._session.flush()

    async def spent_in_month(self, year: int, month: int) -> Decimal:
        """Total ``cost_usd`` in the UTC calendar month."""
        start = datetime(year, month, 1, tzinfo=UTC)
        end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
        total = await self._session.scalar(
            select(func.coalesce(func.sum(LlmCallRow.cost_usd), 0)).where(
                LlmCallRow.created_at >= start, LlmCallRow.created_at < end
            )
        )
        return Decimal(total or 0)
