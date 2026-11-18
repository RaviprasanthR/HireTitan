"""What the drafts workflows share: their dependencies and the validated LLM call."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.drafts.application.ports import JobSource, ProfileFactsSource
from hiretitan.drafts.domain.checks import TechTerms
from hiretitan.platform.clock import ClockPort
from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.port import LlmPort
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.llm.validation import ValidatedLlm

Publish = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class DraftDeps:
    sessions: async_sessionmaker[AsyncSession]
    llm: LlmPort
    prompts: PromptRegistry
    profile: ProfileFactsSource
    jobs: JobSource
    clock: ClockPort
    publish: Publish
    tech_terms: TechTerms = ()
    provider: str = "unknown"


class Recorded:
    """A validated LLM chain that logs every call and remembers the last one (prompt, model)."""

    def __init__(self, deps: DraftDeps, run_id: UUID | None) -> None:
        self.run_id = run_id
        self.calls: list[LlmCallRecord] = []
        self._deps = deps

        async def record(call: LlmCallRecord) -> None:
            async with deps.sessions() as session:
                await CallsRepo(session).record(call)
                await session.commit()
            self.calls.append(call)

        self.chain = ValidatedLlm(deps.llm, record, provider=deps.provider)

    @property
    def last(self) -> LlmCallRecord | None:
        return self.calls[-1] if self.calls else None
