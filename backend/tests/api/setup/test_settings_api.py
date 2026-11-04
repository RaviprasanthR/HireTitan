"""T056: settings endpoints (FR-029, FR-031, FR-032, clarification Q2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.runtime.domain.run_state import PauseReason, RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.setup.api.settings import SettingsApiDeps, create_settings_router


@dataclass
class FakeQueue:
    jobs: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.jobs.append(run_id)


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    queue: FakeQueue


@pytest.fixture
async def env(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path, fake_clock: FakeClock
) -> AsyncIterator[Env]:
    queue = FakeQueue()
    deps = SettingsApiDeps(sessions=sessions, queue=queue, clock=fake_clock, provider="openai")
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_settings_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions, queue)


async def spend(env: Env, usd: str, clock: FakeClock) -> None:
    async with env.sessions() as session:
        await CallsRepo(session).record(
            LlmCallRecord(
                task="extract_profile",
                prompt_name="extract_profile",
                prompt_version="1",
                provider="openai",
                model="gpt-5.4-mini",
                input_tokens=1,
                cached_input_tokens=0,
                output_tokens=1,
                cost_usd=Decimal(usd),
                estimated_cost_usd=Decimal(usd),
                latency_ms=1,
                outcome="ok",
            ),
            created_at=clock.now(),
        )
        await session.commit()


async def test_US3_AS4_settings_show_cap_spend_tiers_status(
    env: Env, fake_clock: FakeClock
) -> None:
    async with env.sessions() as session:
        await ProviderStatusRepo(session).set("openai", "working", None)
        await session.commit()
    await spend(env, "1.250000", fake_clock)

    data = (await env.client.get("/api/v1/settings")).json()

    assert Decimal(data["budget_cap_usd"]) == Decimal("25")
    assert Decimal(data["spent_this_month_usd"]) == Decimal("1.25")
    assert data["key_status"] == "working"
    assert data["tiers"] == [
        {"tier": "fast", "provider": "openai", "model": "gpt-5.4-mini"},
        {"tier": "strong", "provider": "openai", "model": "gpt-6-astra"},
    ]


async def test_missing_status_row_reads_as_unknown(env: Env) -> None:
    data = (await env.client.get("/api/v1/settings")).json()
    assert data["key_status"] == "unknown"


async def test_cap_can_be_changed(env: Env) -> None:
    put = await env.client.put("/api/v1/settings", json={"budget_cap_usd": "40.50"})
    assert put.status_code == 200
    got = (await env.client.get("/api/v1/settings")).json()
    assert Decimal(got["budget_cap_usd"]) == Decimal("40.50")


@pytest.mark.parametrize("value", ["-1", "10000.01", "lots"])
async def test_cap_outside_0_to_10000_is_rejected(env: Env, value: str) -> None:
    res = await env.client.put("/api/v1/settings", json={"budget_cap_usd": value})
    assert res.status_code == 422
    assert res.json()["errors"][0]["field"] == "budget_cap_usd"


async def test_clarification_Q2_tiers_read_only(env: Env) -> None:
    res = await env.client.put(
        "/api/v1/settings",
        json={"budget_cap_usd": "30", "tiers": [{"tier": "fast", "model": "gpt-6-astra"}]},
    )
    assert res.status_code == 422
    tiers = (await env.client.get("/api/v1/settings")).json()["tiers"]
    assert tiers[0]["model"] == "gpt-5.4-mini"


async def test_US3_AS5_raising_cap_resumes_budget_paused_runs(env: Env) -> None:
    async with env.sessions() as session:
        repo = RunsRepo(session)
        budget = await repo.create("profile_ingest")
        key = await repo.create("profile_ingest")
        for run, reason in ((budget, PauseReason.budget_reached), (key, PauseReason.key_missing)):
            await repo.transition(run.id, RunStatus.running)
            await repo.transition(run.id, RunStatus.paused, pause_reason=reason)
        await session.commit()
    await env.client.put("/api/v1/settings", json={"budget_cap_usd": "10"})
    assert env.queue.jobs == []  # lowering the cap resumes nothing

    await env.client.put("/api/v1/settings", json={"budget_cap_usd": "50"})

    assert env.queue.jobs == [budget.id]  # only the budget-paused run
    async with env.sessions() as session:
        assert (await RunsRepo(session).get(budget.id)).state.status is RunStatus.queued  # type: ignore[union-attr]
        assert (await RunsRepo(session).get(key.id)).state.status is RunStatus.paused  # type: ignore[union-attr]


async def test_FR029_settings_never_include_key(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value-123")
    res = await env.client.get("/api/v1/settings")
    assert "sk-secret-value-123" not in res.text
    assert "api_key" not in res.text.lower()
