"""T034: the search run endpoints (contracts/rest-api.md, "Search runs")."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.api_main import create_app
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.config.settings import Settings
from hiretitan.platform.runtime.domain.run_state import RunStatus
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.api.runs import SearchRunsApiDeps, create_search_runs_router
from hiretitan.search.application.synonyms_seed import load_title_synonyms
from hiretitan.search.domain.rules import RuleItem, SearchRules
from hiretitan.search.domain.rules_serialization import rules_to_dict
from hiretitan.search.infra.models import SearchRunRow
from hiretitan.search.infra.repos import (
    CompaniesRepo,
    DecisionsRepo,
    JobsRepo,
    RuleSetsRepo,
    SearchRunsRepo,
)
from hiretitan.search_wiring import ProfileAndPreferencesSource

SEED = Path(__file__).resolve().parents[3] / "seed" / "title_synonyms.yaml"
NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)
RUNS = "/api/v1/search/runs"


@dataclass
class Queue:
    enqueued: list[UUID] = field(default_factory=list)

    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        self.enqueued.append(run_id)


@dataclass
class Setup:
    complete: bool = True

    def gate(self, _session: AsyncSession) -> Setup:
        return self

    async def setup_complete(self) -> bool:
        return self.complete


@dataclass
class Env:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    queue: Queue
    setup: Setup


@pytest.fixture
async def env(sessions: async_sessionmaker[AsyncSession], tmp_path: Path) -> AsyncIterator[Env]:
    queue, setup = Queue(), Setup()
    deps = SearchRunsApiDeps(
        sessions=sessions,
        queue=queue,
        clock=FakeClock(NOW),
        source=ProfileAndPreferencesSource,
        synonyms=load_title_synonyms(SEED),
        setup_gate=setup.gate,
    )
    app = create_app(
        Settings(), frontend_dist=tmp_path / "none", routers=[create_search_runs_router(deps)]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield Env(client, sessions, queue, setup)


async def approve_rules(env: Env) -> None:
    async with env.sessions() as session:
        repo = RuleSetsRepo(session)
        rules = SearchRules(title_words=(RuleItem("Backend Engineer", "user"),))
        await repo.approve((await repo.propose(rules_to_dict(rules), {})).id)
        await session.commit()


async def start(env: Env, mode: str = "rules_only") -> httpx.Response:
    return await env.client.post(RUNS, json={"mode": mode})


async def finish_workflow(env: Env, run_id: UUID) -> None:
    async with env.sessions() as session:
        runs = RunsRepo(session)
        await runs.transition(run_id, RunStatus.running)
        await runs.transition(run_id, RunStatus.done)
        await session.commit()


async def test_FR010_start_returns_202_without_confirmation(env: Env) -> None:
    await approve_rules(env)

    response = await start(env, "rules_and_ai")

    assert response.status_code == 202
    body = response.json()
    assert env.queue.enqueued == [UUID(body["run_id"])]
    detail = (await env.client.get(f"{RUNS}/{body['search_run_id']}")).json()
    assert (detail["mode"], detail["outcome"], detail["batches_done"]) == (
        "rules_and_ai",
        None,
        0,
    )
    assert detail["ai_cost_usd"] == "0.0000"


async def test_start_needs_approved_rules_and_finished_setup(env: Env) -> None:
    response = await start(env)
    assert (response.status_code, response.json()["reason"]) == (409, "rules_not_approved")

    await approve_rules(env)
    env.setup.complete = False
    response = await start(env)
    assert (response.status_code, response.json()["reason"]) == (409, "setup_incomplete")
    assert env.queue.enqueued == []


async def test_FR009_second_start_409(env: Env) -> None:
    await approve_rules(env)
    assert (await start(env)).status_code == 202

    second = await start(env)

    assert (second.status_code, second.json()["reason"]) == (409, "search_already_running")
    assert len(env.queue.enqueued) == 1


async def test_start_rejects_an_unknown_mode(env: Env) -> None:
    await approve_rules(env)
    assert (await start(env, "everything")).status_code == 422


async def test_US1_AS9_stop_endpoint(env: Env) -> None:
    await approve_rules(env)
    body = (await start(env)).json()

    stopped = await env.client.post(f"{RUNS}/{body['search_run_id']}/stop")

    assert stopped.status_code == 202
    detail = (await env.client.get(f"{RUNS}/{body['search_run_id']}")).json()
    assert detail["stop_requested"] is True
    async with env.sessions() as session:
        await SearchRunsRepo(session).finish(
            UUID(body["search_run_id"]), outcome="stopped_by_user", finished_at=NOW
        )
        await session.commit()
    again = await env.client.post(f"{RUNS}/{body['search_run_id']}/stop")
    assert again.status_code == 409
    assert (await env.client.post(f"{RUNS}/{UUID(int=1)}/stop")).status_code == 404


async def test_US1_AS7_summary_says_ai_step_skipped_and_why(env: Env) -> None:
    await approve_rules(env)
    chosen = (await start(env, "rules_only")).json()
    chosen_note = (await env.client.get(f"{RUNS}/{chosen['search_run_id']}")).json()["ai_note"]
    assert "rules only" in chosen_note.lower()
    await finish_workflow(env, UUID(chosen["run_id"]))

    unavailable = (await start(env, "rules_and_ai")).json()
    async with env.sessions() as session:
        await session.execute(
            update(SearchRunRow)
            .where(SearchRunRow.id == UUID(unavailable["search_run_id"]))
            .values(not_checked_by_ai=3, judged_by_ai=0)
        )
        await session.commit()
    note = (await env.client.get(f"{RUNS}/{unavailable['search_run_id']}")).json()["ai_note"]
    assert "not available" in note.lower()

    ok = (await start(env, "rules_and_ai")).status_code
    assert ok == 409  # still active; the note for a normal AI run is empty
    async with env.sessions() as session:
        await session.execute(
            update(SearchRunRow)
            .where(SearchRunRow.id == UUID(unavailable["search_run_id"]))
            .values(not_checked_by_ai=0, judged_by_ai=5)
        )
        await session.commit()
    detail = (await env.client.get(f"{RUNS}/{unavailable['search_run_id']}")).json()
    assert detail["ai_note"] is None


async def test_FR042_history_lists_runs_newest_first(env: Env) -> None:
    await approve_rules(env)
    ids = []
    for _ in range(3):
        body = (await start(env)).json()
        ids.append(body["search_run_id"])
        await finish_workflow(env, UUID(body["run_id"]))

    page = (await env.client.get(RUNS, params={"limit": 2})).json()

    assert [item["id"] for item in page["items"]] == [ids[2], ids[1]]
    assert page["next_cursor"] is not None
    rest = (await env.client.get(RUNS, params={"limit": 2, "cursor": page["next_cursor"]})).json()
    assert [item["id"] for item in rest["items"]] == [ids[0]]
    assert rest["next_cursor"] is None
    latest = (await env.client.get(f"{RUNS.rsplit('/', 1)[0]}/latest")).json()
    assert latest["id"] == ids[2]


async def test_latest_is_null_before_any_search(env: Env) -> None:
    response = await env.client.get("/api/v1/search/latest")
    assert (response.status_code, response.json()) == (200, None)


async def test_skipped_list_has_reasons(env: Env) -> None:
    await approve_rules(env)
    body = (await start(env)).json()
    run_id = UUID(body["search_run_id"])
    async with env.sessions() as session:
        company = await CompaniesRepo(session).add(
            name="Acme", origin="user", resolution="verified"
        )
        jobs = JobsRepo(session)
        for title, state, outcome, why in (
            ("Sales Lead", "skipped", "skipped", "Title is not about your roles"),
            ("Backend Engineer", "explore", "shown", "Fits"),
        ):
            job = await jobs.add(
                company_id=company.id,
                company_name="Acme",
                title=title,
                first_seen_at=NOW,
                last_seen_at=NOW,
                description="d",
                state=state,
            )
            await DecisionsRepo(session).record(
                job.id, outcome=outcome, decided_by="rule", reason=why, search_run_id=run_id
            )
        await session.commit()

    page = (await env.client.get(f"{RUNS}/{run_id}/skipped")).json()

    assert [(i["title"], i["decision"]["reason"]) for i in page["items"]] == [
        ("Sales Lead", "Title is not about your roles")
    ]
