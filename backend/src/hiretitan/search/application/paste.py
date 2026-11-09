"""Adding a job by hand: a link and the pasted description (US4, FR-033).

The person chose this job, so it goes straight to Explore with the reason "added by you" and no AI
is asked about it. The text is untrusted like any posting: it is cleaned and screened, and the
warnings are stored with the job (constitution III). A job already known by its link is not added
twice; the link becomes one more source of the job that is there.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.platform.untrusted.screen import screen
from hiretitan.search.application.search import DecisionInput, NewJob
from hiretitan.search.domain.dedup import DedupJob, fuzzy_candidates
from hiretitan.search.domain.job_state import JobState
from hiretitan.search.domain.normalize import canonical_url, normalize_job

URL_MAX: Final = 1000
DESCRIPTION_MIN: Final = 50
DESCRIPTION_MAX: Final = 30_000
TITLE_MAX: Final = 200
COMPANY_MAX: Final = 120
REASON: Final = "added by you"
SOURCE_KIND: Final = "paste"


@dataclass(frozen=True, slots=True)
class FieldIssue:
    field: str
    message: str


class PasteError(ValueError):
    """Something is missing or wrong; nothing was saved."""

    def __init__(self, errors: list[FieldIssue]) -> None:
        super().__init__("; ".join(e.message for e in errors))
        self.errors = errors


@dataclass(frozen=True, slots=True)
class PasteInput:
    url: str
    description: str
    title: str | None = None
    company: str | None = None


@dataclass(frozen=True, slots=True)
class PasteResult:
    job_id: UUID
    merged_into: UUID | None  # set when the link matched a job that was already there


class PasteStore(Protocol):
    """The database side. Nothing here commits."""

    async def find_by_url(self, canonical: str) -> tuple[UUID, JobState] | None: ...

    async def company_id(self, name: str) -> UUID | None: ...

    async def jobs_of_company(self, name: str) -> list[DedupJob]: ...

    async def insert(self, job: NewJob, now: datetime) -> UUID: ...

    async def add_source(self, job_id: UUID, url: str, now: datetime) -> None: ...

    async def bring_back(self, job_id: UUID, decision: DecisionInput) -> None: ...

    async def add_candidate(self, job_id: UUID, other: UUID, similarity: float) -> None: ...


def _line(text: str) -> str:
    return " ".join(sanitize(text).text.split())


def _check(data: PasteInput) -> tuple[str, str, str, str]:
    """Return the link, the clean description, the title and the company, or raise."""
    errors: list[FieldIssue] = []
    url = data.url.strip()
    canonical = canonical_url(url) if url else None
    if not url:
        errors.append(FieldIssue("url", "Add the link to the job posting."))
    elif len(url) > URL_MAX:
        errors.append(FieldIssue("url", f"The link can be at most {URL_MAX} characters."))
    elif canonical is None:
        errors.append(FieldIssue("url", "The link must start with http:// or https://."))

    raw = data.description.strip()
    description = sanitize(raw).text if raw else ""
    if not raw:
        errors.append(FieldIssue("description", "Paste the job description."))
    elif len(raw) > DESCRIPTION_MAX:
        errors.append(
            FieldIssue(
                "description", f"The description can be at most {DESCRIPTION_MAX:,} characters."
            )
        )
    elif len(description) < DESCRIPTION_MIN:
        errors.append(
            FieldIssue(
                "description", f"The description needs at least {DESCRIPTION_MIN} characters."
            )
        )

    title = _line(data.title) if data.title else ""
    if len(title) > TITLE_MAX:
        errors.append(FieldIssue("title", f"The title can be at most {TITLE_MAX} characters."))
    company = _line(data.company) if data.company else ""
    if len(company) > COMPANY_MAX:
        errors.append(
            FieldIssue("company", f"The company can be at most {COMPANY_MAX} characters.")
        )
    if errors:
        raise PasteError(errors)
    # Left blank, the title is the first line of the text and the company is the link's site:
    # both are taken from what was pasted, never guessed.
    first_line = next((_line(line) for line in description.split("\n") if line.strip()), "")
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    return (
        url,
        description,
        title or first_line[:TITLE_MAX] or host,
        company or host[:COMPANY_MAX],
    )


def _candidates(found: DedupJob, others: list[DedupJob]) -> tuple[tuple[UUID, float], ...]:
    """A pasted job has no place, so it is compared with jobs whose city is known: same company
    and a very similar title. It only raises a notice; the person decides (FR-021)."""
    pairs: dict[UUID, float] = {}
    for other in others:
        if not other.city:
            continue
        for pair in fuzzy_candidates(replace(found, city=other.city), [other]):
            pairs[other.id] = pair.similarity
    return tuple(pairs.items())


async def paste_job(store: PasteStore, data: PasteInput, *, now: datetime) -> PasteResult:
    url, description, title, company = _check(data)
    canonical = canonical_url(url)
    assert canonical is not None  # _check refused anything else
    decision = DecisionInput("shown", "person", REASON)

    known = await store.find_by_url(canonical)
    if known is not None:
        job_id, state = known
        if state is JobState.deleted:
            raise PasteError(
                [FieldIssue("url", "You deleted this job earlier, so it cannot be added again.")]
            )
        await store.add_source(job_id, url, now)
        if state is JobState.skipped:
            await store.bring_back(job_id, decision)
        return PasteResult(job_id, merged_into=job_id)

    flags: list[dict[str, Any]] = [
        {"rule_id": f.rule_id, "severity": f.severity, "excerpt": f.excerpt, "location": f.location}
        for f in screen(f"{title}\n{description}")
    ]
    facts = normalize_job(
        title=title,
        url=url,
        location_text=None,
        posted_at=None,
        description=description,
        requisition_id=None,
        stack_keywords=(),
    )
    candidates = _candidates(
        DedupJob(UUID(int=0), company, None, facts.title, canonical, None, None),
        await store.jobs_of_company(company),
    )
    job_id = await store.insert(
        NewJob(
            company_id=await store.company_id(company),
            company_name=company,
            title=facts.title,
            location_text=None,
            city=None,
            country=None,
            work_mode=facts.work_mode,
            posted_at=None,
            description=description,
            skills_found=facts.skills_found,
            years_found=facts.years_found,
            canonical_url=canonical,
            ats_vendor=None,
            requisition_id=None,
            source_url=url,
            injection_flags=flags,
            decision=decision,
            candidates=candidates,
            source_kind=SOURCE_KIND,
        ),
        now,
    )
    for other, similarity in candidates:
        await store.add_candidate(job_id, other, similarity)
    return PasteResult(job_id, merged_into=None)
