"""Repository for the LLM call log and the monthly spend (FR-012, FR-032)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

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
    latency_ms: int
    outcome: str
    run_id: UUID | None = None


class CallsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, call: LlmCallRecord, *, created_at: datetime | None = None) -> UUID:
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
            latency_ms=call.latency_ms,
            outcome=call.outcome,
        )
        if created_at is not None:
            row.created_at = created_at
        self._session.add(row)
        await self._session.flush()
        return row.id
