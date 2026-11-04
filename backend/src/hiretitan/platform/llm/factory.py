"""Build the LLM port from settings: the provider adapter (or the fake) inside the budget
guard, plus the provider-status service. Both composition roots use this.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.budget import BudgetGuard
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.openai_adapter import PROVIDER, KeyCheck, OpenAiAdapter
from hiretitan.platform.llm.port import LlmPort
from hiretitan.platform.llm.provider_status import ProviderStatusService, Publish


async def _ignore(event: str, data: dict[str, Any]) -> None:
    return None


class _FakeKeyChecker:
    async def check_key(self) -> KeyCheck:
        return "working"


@dataclass(frozen=True, slots=True)
class BuiltLlm:
    llm: LlmPort
    provider_status: ProviderStatusService


def build_llm(
    settings: Settings,
    sessions: async_sessionmaker[AsyncSession],
    cap_provider: Callable[[], Awaitable[Decimal]],
    clock: ClockPort,
    publish: Publish = _ignore,
) -> BuiltLlm:
    catalog = ModelCatalog.load()
    if settings.llm == "fake":
        fake = FakeLlm.from_directory(settings.fake_llm_dir) if settings.fake_llm_dir else FakeLlm()
        status = ProviderStatusService(
            sessions, _FakeKeyChecker(), has_key=True, publish=publish, provider="fake"
        )
        inner: LlmPort = fake
        provider = fake.provider
    else:
        holder: list[ProviderStatusService] = []

        async def on_key_rejected() -> None:
            await holder[0].mark_rejected()

        adapter = OpenAiAdapter(settings.openai_api_key, catalog, on_key_rejected=on_key_rejected)
        status = ProviderStatusService(
            sessions,
            adapter,
            has_key=settings.openai_api_key is not None,
            publish=publish,
            provider=PROVIDER,
        )
        holder.append(status)
        inner, provider = adapter, adapter.provider
    guard = BudgetGuard(
        inner,
        sessions=sessions,
        cap_provider=cap_provider,
        catalog=catalog,
        provider=provider,
        clock=clock,
    )
    return BuiltLlm(guard, status)
