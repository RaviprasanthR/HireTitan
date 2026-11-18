"""Read what a job description asks for, once per description (research R3, spec FR-006).

The description is untrusted: it is sanitised, screened for instructions to an AI (the signals
are stored and shown) and handed to the model inside a data block, by a small fast step whose
output is only a role summary and two short lists. Nothing the description says reaches a
drafting prompt except through those lists.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from hiretitan.drafts.application.ports import JobInfo
from hiretitan.drafts.infra.repos import KeywordsRepo
from hiretitan.drafts.workflow.common import DraftDeps, Recorded
from hiretitan.platform.llm.port import LlmRequest
from hiretitan.platform.llm.validation import Dropped, TaskSpec
from hiretitan.platform.untrusted.delimit import delimit
from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.platform.untrusted.screen import screen
from hiretitan.prompts.extract_job_keywords.v1.checks import tidy

PROMPT_NAME: Final = "extract_job_keywords"


@dataclass(frozen=True, slots=True)
class JobKeywords:
    role_summary: str
    keywords: tuple[str, ...]
    must_have: tuple[str, ...]
    injection_signals: tuple[Any, ...]


EMPTY: Final = JobKeywords("", (), (), ())


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def ensure_keywords(deps: DraftDeps, job: JobInfo, run_id: UUID | None) -> JobKeywords:
    """The job's keywords: stored ones for the same description, else read now.

    ``AiUnavailable`` and ``RetryableLlmError`` propagate, so the run pauses or retries. An answer
    that cannot be used gives empty keywords and stores nothing, so a later try reads again.
    """
    text = sanitize(job.description).text
    digest = _sha(text)
    async with deps.sessions() as session:
        stored = await KeywordsRepo(session).get(job.id)
    if stored is not None and stored.description_sha256 == digest:
        return JobKeywords(
            stored.role_summary, stored.keywords, stored.must_have, stored.injection_signals
        )
    if not text:
        return EMPTY
    signals = [
        {"rule_id": f.rule_id, "severity": f.severity, "excerpt": f.excerpt} for f in screen(text)
    ]
    prompt = deps.prompts.load(PROMPT_NAME)
    request = LlmRequest(
        task=PROMPT_NAME,
        prompt=prompt.render(job_block=delimit("job_posting", text).text),
        output_schema=prompt.output_schema,
        tier=prompt.version.tier,
        max_output_tokens=prompt.version.max_output_tokens,
    )
    schema = prompt.output_schema

    def clean(value: Any) -> tuple[Any, list[Dropped]]:
        return tidy(value), []

    recorded = Recorded(deps, run_id)
    answered = await recorded.chain.run(
        request,
        TaskSpec(
            fallback=lambda: schema.model_validate(
                {"role_summary": "", "keywords": [], "must_have": []}
            ),
            check=clean,
        ),
        run_id=run_id,
    )
    if answered.outcome == "fallback" or recorded.last is None:
        return JobKeywords("", (), (), tuple(signals))
    value = answered.value
    async with deps.sessions() as session:
        await KeywordsRepo(session).save(
            job.id,
            sha256=digest,
            role_summary=value.role_summary,
            keywords=list(value.keywords),
            must_have=list(value.must_have),
            injection_signals=signals,
            prompt_version=str(prompt.version.version),
            model=recorded.last.model,
        )
        await session.commit()
    return JobKeywords(
        value.role_summary, tuple(value.keywords), tuple(value.must_have), tuple(signals)
    )
