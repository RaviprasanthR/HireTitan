"""Check one job with the AI (``POST /jobs/{id}/recheck``): the "Check again" on a job that was
shown as "not checked by AI" (FR-028).

A small workflow so the usual rules apply: an unavailable AI (no key, out of
credit) pauses the run, and "Check again" in the banner puts it back in the queue. An answer
that cannot be used leaves the job as it was.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Final, TypedDict, cast
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.infra.runs_repo import Run
from hiretitan.platform.runtime.runner import WorkflowDef
from hiretitan.search.application.search import DecisionInput, NewJob
from hiretitan.search.domain.job_state import JobState
from hiretitan.search.domain.rules_serialization import rules_from_dict
from hiretitan.search.infra.models import JobRow
from hiretitan.search.infra.repos import DecisionsRepo, JobsRepo, RuleSetsRepo
from hiretitan.search.workflow.describe import describe_job
from hiretitan.search.workflow.graph import FALLBACK_REASON, SearchDeps
from hiretitan.search.workflow.judge import judge_jobs

RECHECK_WORKFLOW: Final = "recheck_job"


class RecheckState(TypedDict, total=False):
    run_id: str
    job_id: str


def _as_new_job(row: JobRow) -> NewJob:
    return NewJob(
        company_id=row.company_id,
        company_name=row.company_name,
        title=row.title,
        location_text=row.location_text,
        city=row.city,
        country=row.country,
        work_mode=row.work_mode,
        posted_at=row.posted_at,
        description=row.description,
        skills_found=tuple(row.skills_found),
        years_found=row.years_found,
        canonical_url=row.canonical_url,
        ats_vendor=row.ats_vendor,
        requisition_id=row.requisition_id,
        source_url="",
        injection_flags=list(row.injection_flags),
        decision=DecisionInput("shown", "rules_only_fallback", FALLBACK_REASON),
        description_status="read" if row.description.strip() else "none",
    )


async def _stack_keywords(session: AsyncSession) -> list[str]:
    """The skills of the approved rules (what a description is searched for)."""
    approved = await RuleSetsRepo(session).approved()
    if approved is None:
        return []
    return [i.text for i in rules_from_dict(approved.rules).stack_keywords]


async def recheck(deps: SearchDeps, state: dict[str, Any]) -> dict[str, Any]:
    if deps.judge is None:
        return {}
    job_id = UUID(state["job_id"])
    async with deps.sessions() as session:
        row = await JobsRepo(session).get(job_id)
        current = await DecisionsRepo(session).current(job_id)
        if row is None or row.state != JobState.explore or current is None:
            return {}
        if current.decided_by != "rules_only_fallback":
            return {}  # someone already decided it
        job = _as_new_job(row)
        keywords = tuple(await _stack_keywords(session))
        kinds = await JobsRepo(session).source_kinds(job_id)
    # A job known only from an alert email is never fetched: the link is the email's, not a
    # company's, and the person opens it and pastes the description (002c FR-015).
    alert_only = kinds == {"email_alert"}
    if deps.descriptions is not None and job.description_status != "read" and not alert_only:
        job = await describe_job(deps.descriptions, job, keywords)
        if job.description_status == "read":  # keep the text: the person sees it on the job
            async with deps.sessions() as session:
                await JobsRepo(session).set_description(
                    job_id,
                    description=job.description,
                    skills_found=job.skills_found,
                    years_found=job.years_found,
                    injection_flags=job.injection_flags,
                )
                await session.commit()
    judged = await judge_jobs(
        deps.judge,
        [job],
        mode="rules_and_ai",
        run_id=UUID(state["run_id"]),
    )
    if judged.unavailable is not None:
        raise judged.unavailable  # the run pauses; "Check again" resumes it
    decision = judged.jobs[0].decision
    if decision.decided_by != "ai":
        return {}  # an unusable answer: the job stays as it was
    async with deps.sessions() as session:
        await DecisionsRepo(session).record(
            job_id,
            outcome=decision.outcome,
            decided_by=decision.decided_by,
            reason=decision.reason,
            **decision.provenance,
        )
        if decision.role:
            await JobsRepo(session).set_role_short(job_id, decision.role)
        if decision.outcome == "skipped":
            await JobsRepo(session).set_state(job_id, JobState.skipped.value)
        await session.commit()
    return {}


def build_graph(deps: SearchDeps) -> StateGraph[Any]:
    graph = StateGraph(RecheckState)
    graph.add_node("recheck", cast(Any, partial(recheck, deps)))
    graph.add_edge(START, "recheck")
    graph.add_edge("recheck", END)
    return graph


def recheck_workflow(deps: SearchDeps) -> WorkflowDef:
    def build(saver: BaseCheckpointSaver[Any]) -> Any:
        return build_graph(deps).compile(checkpointer=saver)

    def initial_input(run: Run) -> dict[str, Any]:
        return {"run_id": str(run.id), "job_id": str(run.subject_id)}

    return WorkflowDef(build=build, initial_input=initial_input)


async def run_recheck(deps: SearchDeps, workflow_run_id: UUID, job_id: UUID) -> None:
    """Run it in-process (tests); the worker uses the registry instead."""
    graph: Any = build_graph(deps).compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": str(workflow_run_id)}}
    await graph.ainvoke({"run_id": str(workflow_run_id), "job_id": str(job_id)}, config)
