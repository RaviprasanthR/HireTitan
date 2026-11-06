"""Fixtures for the W3 graph tests: a fake scanner, a scripted LLM and a profile card."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fakes.career_ops import FakeCareerOps
from tests.fakes.search_env import NOW, Env

import hiretitan.prompts as hiretitan_prompts
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.search.domain.cards import ProfileCard
from hiretitan.search.workflow.graph import SearchDeps
from hiretitan.search.workflow.judge import JudgeDeps

CARD = ProfileCard(
    target_roles=("Backend Engineer",),
    seniority=("junior",),
    years_experience=Decimal(2),
    key_skills=("Python", "FastAPI"),
    preferred_locations=("Pune",),
    work_modes=("remote",),
)


@pytest.fixture
def env(sessions: async_sessionmaker[AsyncSession]) -> Env:
    career_ops = FakeCareerOps()
    llm = FakeLlm()
    published: list[tuple[str, dict[str, object]]] = []

    async def publish(event: str, data: dict[str, object]) -> None:
        published.append((event, data))

    async def card() -> ProfileCard | None:
        return CARD

    deps = SearchDeps(
        sessions=sessions,
        career_ops=career_ops,
        clock=FakeClock(NOW),
        synonyms={},
        publish=publish,
        judge=JudgeDeps(
            sessions=sessions,
            llm=llm,
            profile_card=card,
            prompts=PromptRegistry(Path(hiretitan_prompts.__file__).parent),
        ),
    )
    return Env(sessions, career_ops, deps, published, llm)
