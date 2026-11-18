"""Write one outreach draft (research R7, spec FR-004 to FR-014), modelled on ``recheck``.

One node: load the draft, the job and the confirmed profile; read the job's keywords; ask the
model for the text with placeholders; check it as a statement about the person; fill in the real
first name and the person's own name here, after the checks, so no name ever reaches the model;
check the length of the filled text; repair once; else use a plain template. An unavailable AI
pauses the run (the runner resumes it). The app never sends anything (constitution I): the text is
stored for the person to copy.
"""

from __future__ import annotations

import json
from functools import partial
from typing import Any, Final, TypedDict, cast
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from hiretitan.drafts.application.ports import ConfirmedProfile, JobInfo
from hiretitan.drafts.domain.checks import Problem, check_length, check_text
from hiretitan.drafts.domain.facts import Fact, drafting_facts, years_of_experience
from hiretitan.drafts.domain.fallback import (
    CONNECTION_LIMIT,
    PLACEHOLDER_LEN,
    connection_fallback,
    referral_fallback,
)
from hiretitan.drafts.domain.recipient import fill, first_name
from hiretitan.drafts.domain.selection import allowed_names, select_facts
from hiretitan.drafts.infra.models import OutreachDraftRow
from hiretitan.drafts.infra.repos import DraftsRepo
from hiretitan.drafts.workflow.common import DraftDeps, Recorded
from hiretitan.drafts.workflow.keywords import JobKeywords, ensure_keywords
from hiretitan.platform.llm.port import LlmRequest
from hiretitan.platform.llm.validation import TaskSpec
from hiretitan.platform.runtime.infra.runs_repo import Run
from hiretitan.platform.runtime.runner import WorkflowDef
from hiretitan.platform.untrusted.delimit import delimit
from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.prompts.draft_connection_request.v1.checks import rule_errors as connection_rules
from hiretitan.prompts.draft_referral_message.v1.checks import rule_errors as referral_rules

OUTREACH_WORKFLOW: Final = "outreach_draft"
REFERRAL_LIMIT: Final = 2000
NO_PROFILE: Final = "Finish your profile first, then write a draft."
JOB_GONE: Final = "This job is no longer in your list."
WENT_WRONG: Final = "Something went wrong while writing this draft. You can write it again."
PROMPT_FOR: Final = {
    "connection_request": "draft_connection_request",
    "referral_message": "draft_referral_message",
}


class OutreachState(TypedDict, total=False):
    run_id: str
    draft_id: str


def _job_block(job: JobInfo, keywords: JobKeywords) -> str:
    payload = {
        "job_title": sanitize(job.title).text,
        "company": sanitize(job.company_name).text,
        "role_summary": keywords.role_summary,
        "must_have": list(keywords.must_have),
        "keywords": list(keywords.keywords)[:20],
    }
    return delimit("job_requirements", json.dumps(payload, ensure_ascii=False)).text


def _facts_block(facts: list[Fact]) -> str:
    payload = [{"id": f.id, "text": f.text} for f in facts]
    return delimit("profile_facts", json.dumps(payload, ensure_ascii=False)).text


def _truth_problems(
    text: str,
    cited: list[str],
    all_facts: tuple[Fact, ...],
    profile: ConfirmedProfile,
    job: JobInfo,
    deps: DraftDeps,
    years: int | None,
) -> list[Problem]:
    return check_text(
        text,
        cited,
        all_facts,
        tech_terms=deps.tech_terms,
        allowed_names=allowed_names(profile.view, job.company_name, job.title),
        years=years,
        context=f"{job.title} {job.company_name}",
    )


async def _fail(deps: DraftDeps, draft_id: UUID, job_id: UUID, reason: str) -> None:
    async with deps.sessions() as session:
        await DraftsRepo(session).set_failed(draft_id, reason)
        await session.commit()
    await deps.publish("draft.failed", {"draft_id": str(draft_id), "job_id": str(job_id)})


async def write_draft(deps: DraftDeps, state: dict[str, Any]) -> dict[str, Any]:
    draft_id = UUID(state["draft_id"])
    run_id = UUID(state["run_id"])
    async with deps.sessions() as session:
        draft = await DraftsRepo(session).get(draft_id)
        if draft is None:
            return {}  # deleted while it waited
        snapshot = _Snapshot.of(draft)
    job = await deps.jobs.get(snapshot.job_id)
    if job is None:
        await _fail(deps, draft_id, snapshot.job_id, JOB_GONE)
        return {}
    profile = await deps.profile.current()
    if profile is None:
        await _fail(deps, draft_id, snapshot.job_id, NO_PROFILE)
        return {}

    keywords = await ensure_keywords(deps, job, run_id)  # AiUnavailable pauses the run
    all_facts = drafting_facts(profile.view)
    years = years_of_experience(profile.view, deps.clock.now().date())
    chosen = select_facts(all_facts, [*keywords.must_have, *keywords.keywords], 12)
    first = first_name(snapshot.recipient_name)
    me = profile.view.contact.name

    prompt = deps.prompts.load(PROMPT_FOR[snapshot.kind])
    schema: type[BaseModel] = prompt.output_schema
    recorded = Recorded(deps, run_id)
    variables: dict[str, Any] = {
        "years": years,
        "job_block": _job_block(job, keywords),
        "facts_block": _facts_block(chosen),
    }
    spec: TaskSpec[Any]
    if snapshot.kind == "connection_request":
        room = CONNECTION_LIMIT - (len(first) - PLACEHOLDER_LEN)
        variables["char_budget"] = room
        prompt_rules = connection_rules(first, CONNECTION_LIMIT)

        def rules(output: Any) -> list[str]:
            errors = prompt_rules(output)
            if errors:
                return errors
            found = _truth_problems(
                output.body, list(output.cited_fact_ids), all_facts, profile, job, deps, years
            )
            return [p.message for p in found]

        spec = TaskSpec(
            fallback=lambda: schema.model_validate(
                {
                    "body": connection_fallback(job.title, job.company_name, chosen, first),
                    "cited_fact_ids": [],
                }
            ),
            rules=rules,
        )
        limit = CONNECTION_LIMIT
    else:
        prompt_rules_r = referral_rules(REFERRAL_LIMIT)

        def rules(output: Any) -> list[str]:
            errors = prompt_rules_r(output)
            if errors:
                return errors
            assembled = _assemble(output.greeting, output.body, output.easy_out, output.sign_off)
            found = _truth_problems(
                assembled, list(output.cited_fact_ids), all_facts, profile, job, deps, years
            )
            return [p.message for p in found]

        parts = referral_fallback(job.title, job.company_name, chosen)
        spec = TaskSpec(
            fallback=lambda: schema.model_validate(
                {
                    "greeting": parts.greeting,
                    "body": parts.body,
                    "easy_out": parts.easy_out,
                    "sign_off": parts.sign_off,
                    "cited_fact_ids": [],
                }
            ),
            rules=rules,
        )
        limit = REFERRAL_LIMIT

    request = LlmRequest(
        task=PROMPT_FOR[snapshot.kind],
        prompt=prompt.render(**variables),
        output_schema=prompt.output_schema,
        tier=prompt.version.tier,
        max_output_tokens=prompt.version.max_output_tokens,
    )
    answered = await recorded.chain.run(request, spec, run_id=run_id)
    value = answered.value
    if snapshot.kind == "connection_request":
        template = value.body
    else:
        template = _assemble(value.greeting, value.body, value.easy_out, value.sign_off)
    text = fill(template, first, me)
    if check_length(text, limit):
        # the fallback fits by construction; this only guards an unexpected overrun
        if snapshot.kind == "connection_request":
            template = connection_fallback(job.title, job.company_name, chosen, first)
        else:
            plain = referral_fallback(job.title, job.company_name, chosen)
            template = _assemble(plain.greeting, plain.body, plain.easy_out, plain.sign_off)
        text = fill(template, first, me)[:limit]
        answered_source = "fallback"
    else:
        answered_source = "fallback" if answered.outcome == "fallback" else "ai"
    used = recorded.last if answered_source == "ai" else None
    async with deps.sessions() as session:
        await DraftsRepo(session).save_result(
            draft_id,
            template=template,
            text=text,
            source=answered_source,
            cited_fact_ids=[] if answered_source == "fallback" else list(value.cited_fact_ids),
            prompt_name=used.prompt_name if used else None,
            prompt_version=used.prompt_version if used else None,
            model=used.model if used else None,
        )
        await session.commit()
    await deps.publish("draft.ready", {"draft_id": str(draft_id), "job_id": str(snapshot.job_id)})
    return {}


def _assemble(greeting: str, body: str, easy_out: str, sign_off: str) -> str:
    return f"{greeting}\n\n{body}\n\n{easy_out}\n\n{sign_off}"


class _Snapshot:
    """The few fields of the draft row the node needs, read once so the session can close."""

    def __init__(
        self,
        job_id: UUID,
        kind: str,
        recipient_name: str,
        recipient_kind: str,
    ) -> None:
        self.job_id = job_id
        self.kind = kind
        self.recipient_name = recipient_name
        self.recipient_kind = recipient_kind

    @classmethod
    def of(cls, row: OutreachDraftRow) -> _Snapshot:
        return cls(row.job_id, row.kind, row.recipient_name, row.recipient_kind)


def build_graph(deps: DraftDeps) -> StateGraph[Any]:
    graph = StateGraph(OutreachState)
    graph.add_node("write_draft", cast(Any, partial(write_draft, deps)))
    graph.add_edge(START, "write_draft")
    graph.add_edge("write_draft", END)
    return graph


def outreach_workflow(deps: DraftDeps) -> WorkflowDef:
    def build(saver: BaseCheckpointSaver[Any]) -> Any:
        return build_graph(deps).compile(checkpointer=saver)

    def initial_input(run: Run) -> dict[str, Any]:
        return {"run_id": str(run.id), "draft_id": str(run.subject_id)}

    async def on_failed(run: Run) -> None:
        if run.subject_id is None:
            return
        async with deps.sessions() as session:
            draft = await DraftsRepo(session).get(run.subject_id)
        if draft is not None and draft.status == "writing":
            await _fail(deps, draft.id, draft.job_id, WENT_WRONG)

    return WorkflowDef(build=build, initial_input=initial_input, on_failed=on_failed)


async def run_outreach(deps: DraftDeps, workflow_run_id: UUID, draft_id: UUID) -> None:
    """Run it in-process (tests); the worker uses the registry instead."""
    graph: Any = build_graph(deps).compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": str(workflow_run_id)}}
    await graph.ainvoke({"run_id": str(workflow_run_id), "draft_id": str(draft_id)}, config)
