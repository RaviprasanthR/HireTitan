"""Budget guard (FR-031, FR-032): wraps any ``LlmPort`` and blocks a call before it reaches
the provider when this month's spend plus the call's estimated cost would pass the cap.

The cap comes from an injected provider, so the platform never imports the setup module.
Blocked calls are logged as ``budget_blocked`` (0 tokens, 0 cost, with the estimate).
Calls that pass through are logged by the validation chain, one row per attempt.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from functools import lru_cache

import tiktoken
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.port import AiUnavailable, LlmPort, LlmRequest, LlmResult

_PER_MILLION = Decimal(1_000_000)


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    # disallowed_special=(): resume text may contain strings like "<|endoftext|>".
    return len(_encoding().encode(text, disallowed_special=()))


class BudgetGuard:
    def __init__(
        self,
        inner: LlmPort,
        *,
        sessions: async_sessionmaker[AsyncSession],
        cap_provider: Callable[[], Awaitable[Decimal]],
        catalog: ModelCatalog,
        provider: str,
        clock: ClockPort,
    ) -> None:
        self._inner = inner
        self._sessions = sessions
        self._cap_provider = cap_provider
        self._catalog = catalog
        self._provider = provider
        self._clock = clock

    def estimate(self, req: LlmRequest[BaseModel]) -> tuple[str, Decimal]:
        """(model, estimated USD): input tokens x input price + max output x output price."""
        model = self._catalog.model_for(self._provider, req.tier)
        price = self._catalog.price(model)
        text = "\n".join(
            [req.prompt.system, req.prompt.user, *(block.text for block in req.untrusted_blocks)]
        )
        cost = (count_tokens(text) * price.input + req.max_output_tokens * price.output) / (
            _PER_MILLION
        )
        return model, cost

    async def generate[T: BaseModel](self, req: LlmRequest[T]) -> LlmResult[T]:
        model, estimate = self.estimate(req)
        cap = await self._cap_provider()
        now = self._clock.now()
        async with self._sessions() as session:
            repo = CallsRepo(session)
            spent = await repo.spent_in_month(now.year, now.month)
            if spent + estimate > cap:
                await repo.record(
                    LlmCallRecord(
                        task=req.task,
                        prompt_name=req.prompt.name,
                        prompt_version=str(req.prompt.version),
                        provider=self._provider,
                        model=model,
                        input_tokens=0,
                        cached_input_tokens=0,
                        output_tokens=0,
                        cost_usd=Decimal(0),
                        estimated_cost_usd=estimate,
                        latency_ms=0,
                        outcome="budget_blocked",
                    ),
                    created_at=now,
                )
                await session.commit()
                raise AiUnavailable("budget_reached")
        return await self._inner.generate(req)
