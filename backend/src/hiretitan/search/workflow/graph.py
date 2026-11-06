"""The ``job_search`` graph (W3, contracts/job-search-workflow.md).

plan_run -> next_batch -> fetch_batch -> normalize -> dedup -> apply_rules -> store_batch ->
next_batch ... -> finish. Companies are read in batches of 8; each batch is written in one
transaction before the next starts, so jobs appear as the search goes (FR-008). The relevance
check by the AI is added between ``apply_rules`` and ``store_batch`` (T031).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial
from typing import Any, Final, TypedDict, cast
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import TypeAdapter
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.clock import ClockPort
from hiretitan.platform.runtime.infra.runs_repo import Run
from hiretitan.platform.runtime.runner import WorkflowDef
from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.platform.untrusted.screen import screen
from hiretitan.search.application.ports import BoardRef, CareerOpsPort, ScanError, ScanOk
from hiretitan.search.application.search import (
    BatchWrite,
    CompanyOutcome,
    DecisionInput,
    NewJob,
    SeenJob,
    store_batch,
)
from hiretitan.search.domain.apply_rules import RuleJob, Skip, apply
from hiretitan.search.domain.dedup import DedupJob, exact_match, fuzzy_candidates
from hiretitan.search.domain.normalize import NormalizedJob, normalize_job
from hiretitan.search.domain.rules import SearchRules
from hiretitan.search.domain.rules_serialization import rules_from_dict
from hiretitan.search.domain.vendors import ENABLED_VENDORS
from hiretitan.search.infra.models import JobRow, SearchRunRow
from hiretitan.search.infra.repos import CompaniesRepo, RuleSetsRepo, SearchRunsRepo
from hiretitan.search.infra.search_store import SearchStore

WORKFLOW_NAME: Final = "job_search"
BATCH_SIZE: Final = 8
TITLE_MAX: Final = 200
LOCATION_MAX: Final = 200
DESCRIPTION_MAX: Final = 30_000
CONTINUABLE: Final = ("stopped_by_user", "budget_reached", "out_of_credit", "failed")
FALLBACK_REASON: Final = "not checked by AI"
RECURSION_LIMIT: Final = 100_000

Publish = Callable[[str, dict[str, Any]], Awaitable[None]]
State = dict[str, Any]


@dataclass
class SearchDeps:
    sessions: async_sessionmaker[AsyncSession]
    career_ops: CareerOpsPort
    clock: ClockPort
    synonyms: Mapping[str, tuple[str, ...]]
    publish: Publish | None = None
    batch_size: int = BATCH_SIZE


class SearchState(TypedDict, total=False):
    run_id: str
    search_run_id: str
    index: int
    batch: list[str]
    batch_no: int
    fetched: list[dict[str, Any]]
    outcomes: list[dict[str, Any]]
    prepared: list[dict[str, Any]]
    new: list[dict[str, Any]]
    seen: list[dict[str, Any]]
    ai_cost: str


@dataclass
class Fetched:
    company_id: UUID
    company_name: str
    vendor: str
    title: str
    url: str
    location: str | None
    posted_at: datetime | None
    description: str
    requisition_id: str | None


@dataclass
class Prepared:
    company_id: UUID
    company_name: str
    vendor: str
    source_url: str
    job: NormalizedJob
    description: str
    flags: list[dict[str, str]]


_FETCHED = TypeAdapter(list[Fetched])
_OUTCOMES = TypeAdapter(list[CompanyOutcome])
_PREPARED = TypeAdapter(list[Prepared])
_NEW = TypeAdapter(list[NewJob])
_SEEN = TypeAdapter(list[SeenJob])


def _dump(adapter: TypeAdapter[Any], value: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], adapter.dump_python(value, mode="json"))


def _line(text: str, limit: int) -> str:
    return " ".join(sanitize(text).text.split())[:limit]


async def _run(session: AsyncSession, state: State) -> SearchRunRow:
    run = await SearchRunsRepo(session).get(UUID(state["search_run_id"]))
    assert run is not None
    return run


async def _rules(session: AsyncSession, run: SearchRunRow) -> SearchRules:
    row = await RuleSetsRepo(session).get(run.rule_set_id)
    assert row is not None
    return rules_from_dict(row.rules)


# ---- nodes -----------------------------------------------------------------------------------
async def plan_run(deps: SearchDeps, state: State) -> State:
    """Fix the order the companies are read in: leftovers of the last search first (FR-010a),
    then companies never read, then the longest-ago checked."""
    async with deps.sessions() as session:
        runs = SearchRunsRepo(session)
        run = await runs.by_workflow_run(UUID(state["run_id"]))
        assert run is not None
        if not run.company_order:
            companies = [
                c
                for c in await CompaniesRepo(session).list_readable()
                if c.ats_vendor in ENABLED_VENDORS and c.board_id
            ]
            previous = await runs.previous(run)
            leftover: list[UUID] = []
            if previous is not None and previous.outcome in CONTINUABLE:
                leftover = list(previous.company_order[previous.next_index :])
            known = {c.id for c in companies}
            rest = sorted(
                (c for c in companies if c.id not in leftover),
                key=lambda c: (
                    c.last_checked_at is not None,
                    c.last_checked_at or datetime.min.replace(tzinfo=UTC),
                    c.name.lower(),
                ),
            )
            order = [c for c in leftover if c in known] + [c.id for c in rest]
            await runs.set_company_order(run.id, order)
            await session.commit()
        return {"search_run_id": str(run.id), "index": run.next_index, "ai_cost": "0"}


async def next_batch(deps: SearchDeps, state: State) -> State:
    async with deps.sessions() as session:
        run = await _run(session, state)
        index = state["index"]
        batch = run.company_order[index : index + deps.batch_size]
        return {
            "batch": [str(c) for c in batch],
            "batch_no": run.batches_done + 1,
            "fetched": [],
            "outcomes": [],
            "prepared": [],
            "new": [],
            "seen": [],
        }


def after_next_batch(state: State) -> str:
    return "fetch_batch" if state["batch"] else "finish"


async def fetch_batch(deps: SearchDeps, state: State) -> State:
    refs: list[BoardRef] = []
    names: dict[UUID, str] = {}
    async with deps.sessions() as session:
        repo = CompaniesRepo(session)
        for raw in state["batch"]:
            company = await repo.get(UUID(raw))
            if company is None or not company.ats_vendor or not company.board_id:
                continue
            names[company.id] = company.name
            refs.append(BoardRef(company.id, company.ats_vendor, company.board_id))
    results = await deps.career_ops.scan(refs)  # one company failing never fails the others
    fetched: list[Fetched] = []
    outcomes: list[CompanyOutcome] = []
    for ref in refs:
        result = results.get(ref.company_id, ScanError("No answer from the scanner."))
        if isinstance(result, ScanError):
            outcomes.append(CompanyOutcome(ref.company_id, "failed", 0, result.message[:300]))
            continue
        assert isinstance(result, ScanOk)
        outcomes.append(
            CompanyOutcome(
                ref.company_id, "ok" if result.postings else "no_jobs", len(result.postings), None
            )
        )
        fetched += [
            Fetched(
                ref.company_id,
                names[ref.company_id],
                ref.vendor,
                p.title,
                p.url,
                p.location,
                p.posted_at,
                p.description or "",
                p.requisition_id,
            )
            for p in result.postings
        ]
    return {"fetched": _dump(_FETCHED, fetched), "outcomes": _dump(_OUTCOMES, outcomes)}


async def normalize(deps: SearchDeps, state: State) -> State:
    """Clean every text field, screen it for injection, and read the facts (FR-027)."""
    async with deps.sessions() as session:
        keywords = tuple(
            i.text for i in (await _rules(session, await _run(session, state))).stack_keywords
        )
    prepared: list[Prepared] = []
    for item in _FETCHED.validate_python(state["fetched"]):
        title = _line(item.title, TITLE_MAX)
        if not title:
            continue
        location = _line(item.location, LOCATION_MAX) if item.location else None
        description = sanitize(item.description).text[:DESCRIPTION_MAX]
        flags = [
            {
                "rule_id": f.rule_id,
                "severity": f.severity,
                "excerpt": f.excerpt,
                "location": f.location,
            }
            for f in screen(f"{title}\n{location or ''}\n{description}")
        ]
        job = normalize_job(
            title=title,
            url=item.url,
            location_text=location,
            posted_at=item.posted_at,
            description=description,
            requisition_id=item.requisition_id,
            stack_keywords=keywords,
        )
        prepared.append(
            Prepared(
                item.company_id, item.company_name, item.vendor, item.url, job, description, flags
            )
        )
    return {"prepared": _dump(_PREPARED, prepared)}


def _dedup_job(row: JobRow) -> DedupJob:
    return DedupJob(
        row.id,
        row.company_name,
        row.city,
        row.title,
        row.canonical_url,
        row.ats_vendor,
        row.requisition_id,
    )


async def dedup(deps: SearchDeps, state: State) -> State:
    """Exact matches are the same job seen again; similar ones are only candidates (FR-021)."""
    new: list[NewJob] = []
    seen: list[SeenJob] = []
    batch_keys: set[str] = set()
    async with deps.sessions() as session:
        for item in _PREPARED.validate_python(state["prepared"]):
            job = item.job
            key = job.canonical_url or f"{item.vendor}:{job.requisition_id}:{job.title}"
            if key in batch_keys:
                continue  # the same posting twice in one batch
            batch_keys.add(key)
            clauses = []
            if job.canonical_url:
                clauses.append(JobRow.canonical_url == job.canonical_url)
            if job.requisition_id:
                clauses.append(
                    and_(
                        JobRow.ats_vendor == item.vendor,
                        JobRow.requisition_id == job.requisition_id,
                    )
                )
            candidate = DedupJob(
                UUID(int=0),
                item.company_name,
                job.city,
                job.title,
                job.canonical_url,
                item.vendor,
                job.requisition_id,
            )
            if clauses:
                rows = (await session.scalars(select(JobRow).where(or_(*clauses)))).all()
                found = exact_match(candidate, [_dedup_job(r) for r in rows])
                if found is not None:
                    seen.append(SeenJob(found, item.source_url))
                    continue
            same_company = (
                await session.scalars(
                    select(JobRow).where(
                        func.lower(JobRow.company_name) == item.company_name.lower(),
                        JobRow.state != "deleted",
                    )
                )
            ).all()
            pairs = fuzzy_candidates(candidate, [_dedup_job(r) for r in same_company])
            others = tuple(
                (p.second if p.first == candidate.id else p.first, p.similarity) for p in pairs
            )
            new.append(
                NewJob(
                    company_id=item.company_id,
                    company_name=item.company_name,
                    title=job.title,
                    location_text=job.location_text,
                    city=job.city,
                    country=job.country,
                    work_mode=job.work_mode,
                    posted_at=job.posted_at,
                    description=item.description,
                    skills_found=job.skills_found,
                    years_found=job.years_found,
                    canonical_url=job.canonical_url,
                    ats_vendor=item.vendor,
                    requisition_id=job.requisition_id,
                    source_url=item.source_url,
                    injection_flags=cast(list[dict[str, Any]], item.flags),
                    decision=DecisionInput("shown", "rules_only_fallback", FALLBACK_REASON),
                    candidates=others,
                )
            )
    return {"new": _dump(_NEW, new), "seen": _dump(_SEEN, seen)}


async def apply_rules(deps: SearchDeps, state: State) -> State:
    """The free rules skip obvious noise, with the reason (FR-024). Missing facts never skip."""
    async with deps.sessions() as session:
        rules = await _rules(session, await _run(session, state))
    now = deps.clock.now()
    jobs: list[NewJob] = []
    for job in _NEW.validate_python(state["new"]):
        verdict = apply(
            RuleJob(job.title, job.city, job.country, job.location_text, job.posted_at),
            rules,
            now,
            deps.synonyms,
        )
        if isinstance(verdict, Skip):
            decision = DecisionInput("skipped", "rule", verdict.reason, rule_key=verdict.rule_key)
            job = _with(job, decision)
        jobs.append(job)
    return {"new": _dump(_NEW, jobs)}


def _with(job: NewJob, decision: DecisionInput) -> NewJob:
    fields = {name: getattr(job, name) for name in job.__dataclass_fields__}
    fields["decision"] = decision
    return NewJob(**fields)


async def store_batch_node(deps: SearchDeps, state: State) -> State:
    now = deps.clock.now()
    outcomes = _OUTCOMES.validate_python(state["outcomes"])
    index = state["index"] + len(state["batch"])
    async with deps.sessions() as session:
        companies = CompaniesRepo(session)
        for outcome in outcomes:
            await companies.set_fields(
                outcome.company_id,
                last_checked_at=now,
                last_check_result=outcome.result,
                last_check_error=outcome.error,
            )
        counts = await store_batch(
            SearchStore(session),
            BatchWrite(
                search_run_id=UUID(state["search_run_id"]),
                batch_no=state["batch_no"],
                new=_NEW.validate_python(state["new"]),
                seen=_SEEN.validate_python(state["seen"]),
                companies=outcomes,
                next_index=index,
                ai_cost_delta=Decimal(state.get("ai_cost", "0")),
                now=now,
            ),
        )
    if deps.publish is not None:
        await deps.publish("search.batch_done", counts.progress)
    return {"index": index, "ai_cost": "0"}


async def finish(deps: SearchDeps, state: State) -> State:
    async with deps.sessions() as session:
        await SearchRunsRepo(session).finish(
            UUID(state["search_run_id"]), outcome="finished", finished_at=deps.clock.now()
        )
        await session.commit()
    if deps.publish is not None:
        await deps.publish(
            "search.finished",
            {"search_run_id": state["search_run_id"], "outcome": "finished", "stop_message": None},
        )
    return {}


# ---- graph -----------------------------------------------------------------------------------
def _bound(
    fn: Callable[[SearchDeps, State], Awaitable[State]], deps: SearchDeps
) -> Callable[[State], Awaitable[State]]:
    return partial(fn, deps)


def build_graph(deps: SearchDeps) -> StateGraph[Any]:
    graph = StateGraph(SearchState)
    for name, fn in (
        ("plan_run", plan_run),
        ("next_batch", next_batch),
        ("fetch_batch", fetch_batch),
        ("normalize", normalize),
        ("dedup", dedup),
        ("apply_rules", apply_rules),
        ("store_batch", store_batch_node),
        ("finish", finish),
    ):
        graph.add_node(name, cast(Any, _bound(fn, deps)))
    graph.add_edge(START, "plan_run")
    graph.add_edge("plan_run", "next_batch")
    graph.add_conditional_edges(
        "next_batch", after_next_batch, {"fetch_batch": "fetch_batch", "finish": "finish"}
    )
    graph.add_edge("fetch_batch", "normalize")
    graph.add_edge("normalize", "dedup")
    graph.add_edge("dedup", "apply_rules")
    graph.add_edge("apply_rules", "store_batch")
    graph.add_edge("store_batch", "next_batch")
    graph.add_edge("finish", END)
    return graph


def job_search_workflow(deps: SearchDeps) -> WorkflowDef:
    def build(saver: BaseCheckpointSaver[Any]) -> Any:
        return build_graph(deps).compile(checkpointer=saver)

    def initial_input(run: Run) -> dict[str, Any]:
        return {"run_id": str(run.id)}

    return WorkflowDef(build=build, initial_input=initial_input, recursion_limit=RECURSION_LIMIT)


async def run_search(deps: SearchDeps, workflow_run_id: UUID) -> dict[str, Any]:
    """Run a whole search in-process (tests and tools); the worker uses the registry instead."""
    graph: Any = build_graph(deps).compile(checkpointer=MemorySaver())
    config = {
        "configurable": {"thread_id": str(workflow_run_id)},
        "recursion_limit": RECURSION_LIMIT,
    }
    return cast(dict[str, Any], await graph.ainvoke({"run_id": str(workflow_run_id)}, config))
