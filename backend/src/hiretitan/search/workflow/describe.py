"""Read a posting's own text before the AI check (feature 002i, FR-029).

The listings of most job boards carry only the title, place and link, so the relevance check was
judging on titles. Here a job the free rules kept gets its description read from its source. The
text is untrusted: it is cleaned, screened for injection and capped like any other job text.
A read that fails is not an error: the job simply stays without text and the model is told.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any, Final

from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.platform.untrusted.screen import screen
from hiretitan.search.application.ports import DescribeRequest, DescriptionPort, DescriptionResult
from hiretitan.search.application.search import NewJob
from hiretitan.search.domain.normalize import skills_in, years_in

log = logging.getLogger(__name__)

DESCRIPTION_MAX: Final = 30_000  # as stored with a job
READ_TIMEOUT_SECONDS: Final = 30  # a safety net; the readers have their own, shorter, limits


def _flags(text: str) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": f.rule_id,
            "severity": f.severity,
            "excerpt": f.excerpt,
            "location": f.location,
        }
        for f in screen(text)
    ]


async def describe_job(
    port: DescriptionPort, job: NewJob, stack_keywords: tuple[str, ...]
) -> NewJob:
    """The job with its description read, or marked ``unreadable``. Never raises."""
    request = DescribeRequest(
        url=job.canonical_url or job.source_url,
        ats_vendor=job.ats_vendor,
        requisition_id=job.requisition_id,
    )
    try:
        async with asyncio.timeout(READ_TIMEOUT_SECONDS):
            result = await port.read(request)
    except Exception:  # a reader must never fail the search
        log.exception("Could not read the description of a posting")
        result = DescriptionResult("unreadable")
    text = sanitize(result.text or "").text[:DESCRIPTION_MAX]
    if result.status != "read" or not text.strip():
        return replace(job, description_status="unreadable")
    known = {(f["rule_id"], f["excerpt"]) for f in job.injection_flags}
    fresh = [f for f in _flags(text) if (f["rule_id"], f["excerpt"]) not in known]
    return replace(
        job,
        description=text,
        description_status="read",
        skills_found=skills_in(stack_keywords, job.title, text),
        years_found=years_in(text) or job.years_found,
        injection_flags=[*job.injection_flags, *fresh],
    )
