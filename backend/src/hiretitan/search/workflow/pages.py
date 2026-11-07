"""Reading one company's careers page inside the W3 graph (US3, FR-011, FR-013, research R3).

Order: fetch (robots, spacing, cache, limits) -> JobPosting data and job-shaped links -> the AI,
only when the page has readable text but nothing the free steps could use, and only in
``rules_and_ai`` mode. The AI may give back only links the page itself contains. Any failure is a
result for this one company (``blocked``, ``unreadable``, ``failed``); it never fails the search.
A budget or credit stop is reported in ``PageRead.stop`` so the graph ends the search after the
batch (like the judge).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel

from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.port import AiUnavailable, LlmRequest, RetryableLlmError
from hiretitan.platform.llm.validation import TaskSpec, ValidatedLlm
from hiretitan.prompts.extract_jobs_from_page.v1.checks import rule_errors
from hiretitan.search.application.extract_page_prompt import render_extract_prompt
from hiretitan.search.application.ports import PageFetcherPort, Posting
from hiretitan.search.infra.careers_page.parse import parse_careers_page
from hiretitan.search.infra.careers_page.text import page_links, page_text
from hiretitan.search.workflow.judge import JudgeDeps
from hiretitan.search.workflow.stops import Stop, stop_for

PROMPT_NAME: Final = "extract_jobs_from_page"
ERROR_MAX: Final = 300
UNREADABLE: Final = "This page shows no job list we can read. Check it yourself."
NO_REPLY: Final = "The AI could not read this page. Check it yourself."


@dataclass
class PageRead:
    result: str  # ok | no_jobs | blocked | unreadable | failed
    postings: list[Posting] = field(default_factory=list)
    error: str | None = None
    cost: Decimal = Decimal(0)
    stop: Stop | None = None


def _only_links_from(allowed: frozenset[str]) -> Callable[[Any], list[str]]:
    def check(output: Any) -> list[str]:
        return [
            f"The link for {job.title!r} is not a link given in the page text. "
            "Use only links that appear in the page text."
            for job in output.jobs
            if job.url not in allowed
        ]

    return check


async def _ask_ai(
    deps: JudgeDeps, text: str, url: str, *, run_id: UUID
) -> tuple[list[Posting] | None, Decimal, Stop | None, str | None]:
    """The jobs the AI found (None: no usable answer), what it cost, a stop, and an error."""
    cost = Decimal(0)

    async def record(call: LlmCallRecord) -> None:
        nonlocal cost
        async with deps.sessions() as session:
            await CallsRepo(session).record(call)
            await session.commit()
        cost += call.cost_usd

    prompt = deps.prompts.load(PROMPT_NAME)
    schema: type[BaseModel] = prompt.output_schema
    host = urlsplit(url).hostname or ""
    own_rules = rule_errors(host)
    on_page = page_links(text)
    link_rules = _only_links_from(on_page)

    def rules(output: Any) -> list[str]:
        return own_rules(output) + link_rules(output)

    request = LlmRequest(
        task=PROMPT_NAME,
        prompt=render_extract_prompt(prompt, text, url),
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
                rules=rules,
                allowed_links=on_page,
            ),
            run_id=run_id,
        )
    except AiUnavailable as exc:
        return None, cost, stop_for(exc), (exc.provider_message or str(exc))[:ERROR_MAX]
    except RetryableLlmError as exc:
        return None, cost, None, str(exc)[:ERROR_MAX]
    if answered.outcome == "fallback":
        return None, cost, None, None
    found = [Posting(job.title, job.url, job.location) for job in answered.value.jobs]
    return found, cost, None, None


async def read_careers_page(
    pages: PageFetcherPort | None,
    ai: JudgeDeps | None,
    url: str,
    *,
    use_ai: bool,
    run_id: UUID,
) -> PageRead:
    """Read one careers page; ``use_ai`` is true only in AI mode with the page step switched on."""
    if pages is None:
        return PageRead("unreadable", error="Careers pages cannot be read here.")
    fetched = await pages.fetch(url)
    if fetched.status != "ok" or fetched.body is None:
        error = (fetched.error or UNREADABLE)[:ERROR_MAX]
        status = fetched.status if fetched.status in ("blocked", "unreadable") else "failed"
        return PageRead(status, error=error)
    base = fetched.final_url or url
    parsed = parse_careers_page(fetched.body, base)
    if parsed.status == "found":
        return PageRead("ok", list(parsed.postings))
    if parsed.status == "unreadable":
        return PageRead("unreadable", error=UNREADABLE)
    if not use_ai or ai is None:  # readable text, no jobs we can pick out without the AI
        return PageRead("no_jobs")
    text = page_text(fetched.body, base)
    found, cost, stop, ai_error = await _ask_ai(ai, text, base, run_id=run_id)
    if found is None:
        outcome = "unreadable" if ai_error is None else "failed"
        return PageRead(outcome, error=ai_error or NO_REPLY, cost=cost, stop=stop)
    return PageRead("ok" if found else "no_jobs", found, cost=cost)
