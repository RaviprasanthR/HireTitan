"""The ``judge_relevance`` step of the W3 graph (US1, FR-026, FR-028, FR-035a).

Jobs that passed the free rules go to the fast model 10 at a time. A usable answer decides each
job ("shown" or "skipped", with the model's reason and where it came from). Anything else keeps
the job in Explore as "not checked by AI": no key, rules-only mode, or an answer the validation
chain could not use after its one repair (FR-028). A credit stop is not swallowed here:
it is reported in ``Judged.stop`` so the graph ends the search after storing the batch (T032).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.port import AiUnavailable, LlmPort, LlmRequest, RetryableLlmError
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.llm.validation import TaskSpec, ValidatedLlm
from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.prompts.judge_relevance.v2.checks import rule_errors
from hiretitan.search.application.judge_prompt import render_judge_prompt
from hiretitan.search.application.search import DecisionInput, NewJob
from hiretitan.search.domain.cards import JOBS_PER_CALL_MAX, JobCardInput, ProfileCard
from hiretitan.search.workflow.stops import Stop, stop_for

PROMPT_NAME: Final = "judge_relevance"
REASON_MAX: Final = 160
ROLE_MAX: Final = 60

ProfileCardSource = Callable[[], Awaitable[ProfileCard | None]]


@dataclass
class JudgeDeps:
    sessions: async_sessionmaker[AsyncSession]
    llm: LlmPort
    profile_card: ProfileCardSource
    prompts: PromptRegistry
    provider: str = "unknown"


@dataclass
class Judged:
    jobs: list[NewJob]
    stop: Stop | None = None  # out of credit: the search ends after this batch
    unavailable: AiUnavailable | None = None  # why the AI could not answer, for any reason


def with_decision(job: NewJob, decision: DecisionInput) -> NewJob:
    fields = {name: getattr(job, name) for name in job.__dataclass_fields__}
    fields["decision"] = decision
    return NewJob(**fields)


def _card(job: NewJob) -> JobCardInput:
    return JobCardInput(
        title=job.title,
        company=job.company_name,
        location=job.location_text,
        work_mode=job.work_mode,
        skills_found=job.skills_found,
        years_found=job.years_found,
        description=job.description,
    )


def _role(decision: object) -> str | None:
    """The model's short role, cleaned; none when it gave none."""
    raw = getattr(decision, "role", None)
    if not raw:
        return None
    return " ".join(sanitize(raw).text.split())[:ROLE_MAX] or None


async def judge_jobs(deps: JudgeDeps, jobs: list[NewJob], *, mode: str, run_id: UUID) -> Judged:
    """Judge the jobs that the rules kept; leave every other job as it is."""
    result = Judged(list(jobs))
    pending = [i for i, j in enumerate(jobs) if j.decision.decided_by == "rules_only_fallback"]
    if not pending or mode != "rules_and_ai":
        return result
    card = await deps.profile_card()
    if card is None:
        return result
    prompt = deps.prompts.load(PROMPT_NAME)
    schema: type[BaseModel] = prompt.output_schema
    calls: list[tuple[UUID, LlmCallRecord]] = []

    async def record(call: LlmCallRecord) -> None:
        async with deps.sessions() as session:
            call_id = await CallsRepo(session).record(call)
            await session.commit()
        calls.append((call_id, call))

    chain = ValidatedLlm(deps.llm, record, provider=deps.provider)
    for start in range(0, len(pending), JOBS_PER_CALL_MAX):
        chunk = pending[start : start + JOBS_PER_CALL_MAX]
        built = render_judge_prompt(prompt, card, [_card(jobs[i]) for i in chunk])
        request = LlmRequest(
            task=PROMPT_NAME,
            prompt=built.prompt,
            output_schema=prompt.output_schema,
            tier="fast",
            max_output_tokens=prompt.version.max_output_tokens,
        )
        calls.clear()
        try:
            answered = await chain.run(
                request,
                TaskSpec(
                    fallback=lambda: schema.model_validate({"decisions": []}),
                    rules=rule_errors(built.refs, [jobs[i].title for i in chunk]),
                ),
                run_id=run_id,
            )
        except AiUnavailable as exc:
            result.unavailable = exc
            result.stop = stop_for(exc)  # None for a key problem: rules carry on (FR-028)
            break  # this call's jobs and the rest stay "not checked by AI"
        except RetryableLlmError:
            continue  # a temporary provider error is not a stop (FR-028)
        if answered.outcome == "fallback" or not calls:
            continue  # this call's jobs stay "not checked by AI"
        call_id, call = calls[-1]
        said = {d.ref: d for d in answered.value.decisions}
        for ref, index in zip(built.refs, chunk, strict=True):
            decision = said[ref]
            result.jobs[index] = with_decision(
                jobs[index],
                DecisionInput(
                    "shown" if decision.relevant else "skipped",
                    "ai",
                    " ".join(sanitize(decision.reason).text.split())[:REASON_MAX],
                    role=_role(decision),
                    provenance={
                        "prompt_name": call.prompt_name,
                        "prompt_version": call.prompt_version,
                        "provider": call.provider,
                        "model": call.model,
                        "llm_call_id": call_id,
                    },
                ),
            )
    return result
