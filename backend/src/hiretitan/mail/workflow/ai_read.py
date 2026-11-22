"""Reading an alert email with the AI when no fixed reader can (feature 002c, FR-013a, FR-014).

The email is untrusted: its words and its numbered links go to the AI inside marked data blocks,
and the AI answers with a title, a company, a place and the *number* of a link. The answer is
checked against the email (``mail.domain.alert_checks``), so nothing the AI invents, and no address
it makes up, can reach a job. Only the email's own links are ever used, and none is ever opened.

* ``AiUnavailable`` (no key, a rejected key, out of credit, over budget) and a temporary provider
  error are raised as ``MailAiUnavailableError``: the email waits for the next check (``needs_ai``).
* An answer that stays unusable after the repair attempts gives ``None``: the email is counted as
  one that could not be read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.mail.application.alert_prompt import render_alert_prompt, shown_links
from hiretitan.mail.domain.alert_checks import Proposed, accept
from hiretitan.mail.domain.alerts import AlertJob
from hiretitan.mail.domain.mime import Flat
from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.port import AiUnavailable, LlmPort, LlmRequest, RetryableLlmError
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.llm.validation import TaskSpec, ValidatedLlm
from hiretitan.prompts.read_job_alert.v1.checks import rule_errors

PROMPT_NAME: Final = "read_job_alert"
AI_EMAILS_MAX: Final = 30  # emails sent to the AI in one check: the cost has a ceiling


class MailAiUnavailableError(Exception):
    """The AI cannot be asked right now; the email is kept for the next check."""


@dataclass(frozen=True)
class MailAiDeps:
    sessions: async_sessionmaker[AsyncSession]
    llm: LlmPort
    prompts: PromptRegistry
    provider: str = "openai"


async def read_with_ai(
    deps: MailAiDeps, flat: Flat, *, site: str, alert_date: datetime, run_id: UUID
) -> list[AlertJob] | None:
    """The jobs the email backs up (possibly none), or ``None`` when there was no usable answer.
    Raises ``MailAiUnavailableError`` when the AI cannot be asked."""

    async def record(call: LlmCallRecord) -> None:
        async with deps.sessions() as session:
            await CallsRepo(session).record(call)
            await session.commit()

    prompt = deps.prompts.load(PROMPT_NAME)
    schema: type[BaseModel] = prompt.output_schema
    shown = len(shown_links(flat))
    request = LlmRequest(
        task=PROMPT_NAME,
        prompt=render_alert_prompt(prompt, flat),
        output_schema=schema,
        tier="fast",
        max_output_tokens=prompt.version.max_output_tokens,
    )
    chain = ValidatedLlm(deps.llm, record, provider=deps.provider)
    try:
        answered = await chain.run(
            request,
            TaskSpec(
                fallback=lambda: schema.model_validate({"jobs": []}),
                rules=rule_errors(shown),
            ),
            run_id=run_id,
        )
    except (AiUnavailable, RetryableLlmError) as error:
        raise MailAiUnavailableError(str(error)) from error
    if answered.outcome == "fallback":
        return None
    jobs: list[Any] = answered.value.jobs
    proposed = [Proposed(j.title, j.company, j.location, j.link_index) for j in jobs]
    return accept(proposed, flat, site=site, alert_date=alert_date, shown=shown)
