"""Tailor the confirmed profile into a resume for one job (research R7, spec FR-015 to FR-019).

One node, like ``outreach``: read the job's keywords, ask the strong model to reword and reorder the
person's own facts, check every id, number, technology and skill against the profile, repair once,
else fall back to the profile in its own wording ordered by the job's keywords. The document is
built from the profile by id, so employers, titles, dates and schools cannot be invented.
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

from hiretitan.drafts.domain.facts import drafting_facts, years_of_experience
from hiretitan.drafts.domain.keywords import backed, match
from hiretitan.drafts.domain.resume_doc import (
    ResumeDocument,
    build_from_profile,
    document_text,
    plain_reorder,
)
from hiretitan.drafts.domain.selection import allowed_names
from hiretitan.drafts.domain.tailor_checks import check_choice
from hiretitan.drafts.infra.repos import TailoredRepo
from hiretitan.drafts.workflow.common import DraftDeps, Recorded
from hiretitan.drafts.workflow.keywords import ensure_keywords
from hiretitan.platform.llm.port import LlmRequest
from hiretitan.platform.llm.validation import TaskSpec
from hiretitan.platform.runtime.infra.runs_repo import Run
from hiretitan.platform.runtime.runner import WorkflowDef
from hiretitan.platform.untrusted.delimit import delimit
from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.prompts.tailor_resume.v1.checks import choice_of

TAILOR_WORKFLOW: Final = "tailor_resume"
PROMPT_NAME: Final = "tailor_resume"
NO_PROFILE: Final = "Finish your profile first, then tailor a resume."
JOB_GONE: Final = "This job is no longer in your list."
NO_DESCRIPTION: Final = "Add the job description first."
WENT_WRONG: Final = "Something went wrong while tailoring this resume. You can tailor it again."
DESCRIPTION_MIN: Final = 200


class TailorState(TypedDict, total=False):
    run_id: str
    job_id: str


async def _fail(deps: DraftDeps, job_id: UUID, reason: str) -> None:
    async with deps.sessions() as session:
        await TailoredRepo(session).set_failed(job_id, reason)
        await session.commit()
    await deps.publish("tailored_resume.failed", {"job_id": str(job_id)})


def _profile_block(profile: Any) -> str:
    payload = {
        "summary": profile.summary or profile.headline or "",
        "experience": [
            {
                "experience_id": job.id,
                "title": job.title,
                "employer": job.employer,
                "bullets": [{"index": i, "text": b} for i, b in enumerate(job.bullets)],
            }
            for job in profile.experience
        ],
        "skills": list(profile.skills),
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "technologies": list(p.technologies),
            }
            for p in profile.projects
        ],
    }
    return delimit("profile", json.dumps(payload, ensure_ascii=False)).text


async def tailor(deps: DraftDeps, state: dict[str, Any]) -> dict[str, Any]:
    job_id = UUID(state["job_id"])
    run_id = UUID(state["run_id"])
    job = await deps.jobs.get(job_id)
    if job is None:
        return {}  # deleted while it waited: its rows went with it
    if len(job.description.strip()) < DESCRIPTION_MIN:
        await _fail(deps, job_id, NO_DESCRIPTION)
        return {}
    profile = await deps.profile.current()
    if profile is None:
        await _fail(deps, job_id, NO_PROFILE)
        return {}
    view = profile.view

    keywords = await ensure_keywords(deps, job, run_id)  # AiUnavailable pauses the run
    all_keywords = list(dict.fromkeys([*keywords.must_have, *keywords.keywords]))
    wanted = backed(all_keywords, view)
    facts = drafting_facts(view)
    years = years_of_experience(view, deps.clock.now().date())
    names = allowed_names(view, job.company_name, job.title)
    context = f"{job.title} {job.company_name}"

    prompt = deps.prompts.load(PROMPT_NAME)
    schema: type[BaseModel] = prompt.output_schema
    job_payload = {
        "job_title": sanitize(job.title).text,
        "company": sanitize(job.company_name).text,
        "role_summary": keywords.role_summary,
        "must_have": list(keywords.must_have),
        "keywords_the_profile_can_support": [k for k in all_keywords if k in wanted],
    }
    request = LlmRequest(
        task=PROMPT_NAME,
        prompt=prompt.render(
            years=years,
            job_block=delimit("job_requirements", json.dumps(job_payload, ensure_ascii=False)).text,
            profile_block=_profile_block(view),
        ),
        output_schema=prompt.output_schema,
        tier=prompt.version.tier,
        max_output_tokens=prompt.version.max_output_tokens,
    )

    def rules(output: Any) -> list[str]:
        found = check_choice(
            choice_of(output),
            view,
            facts,
            tech_terms=deps.tech_terms,
            allowed_names=names,
            years=years,
            context=context,
        )
        return [p.message for p in found]

    fallback_doc = plain_reorder(view, all_keywords)
    recorded = Recorded(deps, run_id)
    answered = await recorded.chain.run(
        request,
        TaskSpec(
            fallback=lambda: schema.model_validate(
                {"summary": fallback_doc.summary, "experience": [], "skills": [], "project_ids": []}
            ),
            rules=rules,
        ),
        run_id=run_id,
    )
    if answered.outcome == "fallback":
        doc: ResumeDocument = fallback_doc
        source = "fallback"
        used = None
    else:
        doc = build_from_profile(view, choice_of(answered.value))
        source = "ai"
        used = recorded.last
    result = match(all_keywords, document_text(doc), wanted)
    async with deps.sessions() as session:
        await TailoredRepo(session).save_result(
            job_id,
            document=doc.model_dump(mode="json"),
            keyword_match=result.to_dict(),
            source=source,
            profile_version_id=profile.version_id,
            prompt_name=used.prompt_name if used else None,
            prompt_version=used.prompt_version if used else None,
            model=used.model if used else None,
        )
        await session.commit()
    await deps.publish("tailored_resume.ready", {"job_id": str(job_id)})
    return {}


def build_graph(deps: DraftDeps) -> StateGraph[Any]:
    graph = StateGraph(TailorState)
    graph.add_node("tailor", cast(Any, partial(tailor, deps)))
    graph.add_edge(START, "tailor")
    graph.add_edge("tailor", END)
    return graph


def tailor_workflow(deps: DraftDeps) -> WorkflowDef:
    def build(saver: BaseCheckpointSaver[Any]) -> Any:
        return build_graph(deps).compile(checkpointer=saver)

    def initial_input(run: Run) -> dict[str, Any]:
        return {"run_id": str(run.id), "job_id": str(run.subject_id)}

    async def on_failed(run: Run) -> None:
        if run.subject_id is None:
            return
        async with deps.sessions() as session:
            row = await TailoredRepo(session).get_for_job(run.subject_id)
        if row is not None and row.status == "writing":
            await _fail(deps, row.job_id, WENT_WRONG)

    return WorkflowDef(build=build, initial_input=initial_input, on_failed=on_failed)


async def run_tailor(deps: DraftDeps, workflow_run_id: UUID, job_id: UUID) -> None:
    """Run it in-process (tests); the worker uses the registry instead."""
    graph: Any = build_graph(deps).compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": str(workflow_run_id)}}
    await graph.ainvoke({"run_id": str(workflow_run_id), "job_id": str(job_id)}, config)
