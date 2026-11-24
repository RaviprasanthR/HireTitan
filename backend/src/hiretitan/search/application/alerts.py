"""Jobs found in alert emails, into the search tables (feature 002c, FR-018 to FR-024).

The mail module hands over neutral ``AlertPosting`` records; this module applies the search's own
rules, deduplication and batch writer, so an alert job is treated exactly like one from any other
source. Two things differ, both on purpose:

* An alert has no description, so the AI relevance check is never asked (FR-018): a job the free
  rules keep is shown as "Not checked by AI: no description yet".
* A company the list does not know is **shown, not created** (FR-018a): ``company_id`` comes from a
  lookup by name and stays empty when there is none.

An email can mention a posting that is already known (an earlier alert, a searched board, a pasted
job): then it only adds a source and a sighting. A near match is a *candidate* for the person to
judge, never a merge. A posting already in the pipeline is listed once more only as left out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Protocol
from uuid import UUID

from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.search.application.search import (
    BatchWrite,
    DecisionInput,
    NewJob,
    SearchTransaction,
    SeenJob,
    store_batch,
)
from hiretitan.search.domain.apply_rules import RuleJob, Skip, apply
from hiretitan.search.domain.dedup import (
    DedupJob,
    exact_match,
    fuzzy_candidates,
    same_posting_again,
)
from hiretitan.search.domain.normalize import canonical_url, normalize_job
from hiretitan.search.domain.rules import SearchRules
from hiretitan.search.domain.tech_names import TechTable

SOURCE_KIND: Final = "email_alert"
PIPELINE_STATES: Final = ("applied", "inquired")
NO_COMPANY: Final = "Company not shown in the alert"
FALLBACK_REASON: Final = "Not checked by AI: no description yet"
SOURCE_URL_MAX: Final = 1000
TITLE_MAX: Final = 200
COMPANY_MAX: Final = 120
LOCATION_MAX: Final = 120


@dataclass(frozen=True, slots=True)
class AlertPosting:
    """One job as one alert email showed it. ``clean_link`` is the posting's address without
    tracking (the key repeats are recognised by); ``link`` is exactly what the email gave."""

    title: str
    company: str | None
    location: str | None
    link: str
    clean_link: str
    posting_id: str | None
    site: str
    alert_date: datetime
    posted_at: datetime | None
    injection_signals: list[dict[str, Any]]
    read_message_id: UUID | None
    read_by: str = "fixed"  # who gave the company and place: "fixed" or "ai" (FR-013d)


@dataclass(frozen=True, slots=True)
class AlertReading:
    """A new reading of a job already stored: what may fix its company and place (FR-013d)."""

    company: str | None
    company_id: UUID | None
    location_text: str | None
    city: str | None
    country: str | None
    work_mode: str | None
    read_by: str


@dataclass(frozen=True, slots=True)
class AlertCounts:
    """What happened to a batch of postings. They add up: ``found`` is every posting stored."""

    new: int = 0  # added to Explore
    already_known: int = 0  # a posting that was already a job: a source and a sighting only
    left_out: int = 0  # kept out by the free rules (restorable)
    already_in_pipeline: int = 0
    possible_duplicates: int = 0
    in_pipeline_titles: tuple[str, ...] = ()
    progress: dict[str, Any] = field(default_factory=dict)

    @property
    def found(self) -> int:
        return self.new + self.already_known + self.left_out + self.already_in_pipeline


@dataclass(frozen=True, slots=True)
class Sighting:
    read_message_id: UUID | None
    site: str
    link: str
    alert_date: datetime
    posted_at: datetime | None


@dataclass(frozen=True, slots=True)
class KnownJob:
    dedup: DedupJob
    state: str


class AlertStore(SearchTransaction, Protocol):
    """The search transaction plus what alerts need. Nothing here creates a company."""

    async def exact_matches(
        self, canonical: str | None, vendor: str | None, requisition_id: str | None
    ) -> list[KnownJob]: ...

    async def jobs_of_company(self, name: str) -> list[KnownJob]: ...

    async def company_id(self, name: str) -> UUID | None: ...

    async def refresh_alert_job(self, job_id: UUID, reading: AlertReading) -> None:
        """Fix the company and place of a job known only from alerts (FR-013d)."""
        ...

    def queue_sighting(self, source_url: str, sighting: Sighting) -> None:
        """Note a sighting of the job this batch inserts under ``source_url``; written with it."""
        ...

    def queue_sighting_for_job(self, job_id: UUID, sighting: Sighting) -> None: ...


def facts_url(url: str) -> str:
    """The address as the search keeps it (tracking and a trailing slash dropped)."""
    return canonical_url(url) or url


def _line(text: str, size: int) -> str:
    return " ".join(sanitize(text).text.split())[:size]


def _flags(signals: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Signals found in the email travel with the job, marked as coming from the email."""
    return [{**dict(signal), "location": "email"} for signal in signals]


async def store_alert_postings(
    store: AlertStore,
    *,
    search_run_id: UUID,
    batch_no: int,
    postings: Sequence[AlertPosting],
    rules: SearchRules,
    synonyms: Mapping[str, tuple[str, ...]],
    tech_names: TechTable,
    now: datetime,
) -> AlertCounts:
    """Store one batch of alert postings in a single transaction (the caller's session)."""
    keywords = tuple(item.text for item in rules.stack_keywords)
    new: list[NewJob] = []
    seen: list[SeenJob] = []
    in_pipeline_titles: list[str] = []
    batch_keys: dict[str, int] = {}  # clean link -> index into ``new``
    # the other ways one posting shows twice in a batch: the same normalised address, or the same
    # posting number on one site. The jobs are not stored until the batch is, so the database
    # look-ups cannot see them yet.
    in_batch: dict[str, str] = {}  # key -> the clean link of the job it belongs to
    possible = 0
    pipeline_again = 0
    known_by_key: dict[str, UUID] = {}

    for posting in postings:
        title = _line(posting.title, TITLE_MAX)
        source_url = posting.clean_link.strip()
        if not title or not source_url or len(source_url) > SOURCE_URL_MAX:
            continue  # nothing a person could use: never stored
        sighting = Sighting(
            posting.read_message_id,
            posting.site,
            posting.link,
            posting.alert_date,
            posting.posted_at,
        )
        same_in_batch = in_batch.get(f"url:{facts_url(source_url)}") or (
            in_batch.get(f"id:{posting.site}:{posting.posting_id}") if posting.posting_id else None
        )
        if same_in_batch is not None and same_in_batch != source_url:
            store.queue_sighting(same_in_batch, sighting)
            continue
        if source_url in batch_keys or source_url in known_by_key:
            # the same posting again in this batch: one more sighting of the job
            if source_url in known_by_key:
                store.queue_sighting_for_job(known_by_key[source_url], sighting)
            else:
                store.queue_sighting(source_url, sighting)
            continue
        company = _line(posting.company, COMPANY_MAX) if posting.company else ""
        location = _line(posting.location, LOCATION_MAX) if posting.location else None
        facts = normalize_job(
            title=title,
            url=source_url,
            location_text=location or None,
            posted_at=posting.posted_at,
            description="",
            requisition_id=posting.posting_id,
            stack_keywords=keywords,
        )
        candidate = DedupJob(
            UUID(int=0),
            company or NO_COMPANY,
            facts.city,
            facts.title,
            facts.canonical_url,
            posting.site,
            posting.posting_id,
        )
        matches = await store.exact_matches(facts.canonical_url, posting.site, posting.posting_id)
        found = exact_match(candidate, [k.dedup for k in matches])
        if found is not None:
            seen.append(SeenJob(found, source_url, SOURCE_KIND))
            known_by_key[source_url] = found
            store.queue_sighting_for_job(found, sighting)
            if company or facts.location_text:
                await store.refresh_alert_job(
                    found,
                    AlertReading(
                        company=company or None,
                        company_id=await store.company_id(company) if company else None,
                        location_text=facts.location_text,
                        city=facts.city,
                        country=facts.country,
                        work_mode=facts.work_mode,
                        read_by=posting.read_by,
                    ),
                )
            matched = next(k for k in matches if k.dedup.id == found)
            if matched.state in PIPELINE_STATES:
                pipeline_again += 1  # the same link as a job in the pipeline: counted there
            continue

        decision: DecisionInput
        others: tuple[tuple[UUID, float], ...] = ()
        pipeline_title: str | None = None
        if company:
            same_company = await store.jobs_of_company(company)
            pairs = fuzzy_candidates(
                candidate, [k.dedup for k in same_company if k.state != "deleted"]
            )
            others = tuple(
                (p.second if p.first == candidate.id else p.first, p.similarity) for p in pairs
            )
            in_pipeline = next(
                (
                    k
                    for k in same_company
                    if k.state in PIPELINE_STATES and same_posting_again(candidate, k.dedup)
                ),
                None,
            )
            pipeline_title = in_pipeline.dedup.title if in_pipeline else None
        if pipeline_title is not None:
            decision = DecisionInput(
                "skipped",
                "rule",
                f"Already in your pipeline as {pipeline_title}.",
                rule_key="already_in_pipeline",
            )
            in_pipeline_titles.append(pipeline_title)
        else:
            verdict = apply(
                RuleJob(
                    facts.title, facts.city, facts.country, facts.location_text, facts.posted_at
                ),
                rules,
                now,
                synonyms,
                tech_names,
            )
            decision = (
                DecisionInput("skipped", "rule", verdict.reason, rule_key=verdict.rule_key)
                if isinstance(verdict, Skip)
                else DecisionInput("shown", "rules_only_fallback", FALLBACK_REASON)
            )
        if others and decision.outcome == "shown":
            possible += 1
        batch_keys[source_url] = len(new)
        if facts.canonical_url:
            in_batch[f"url:{facts.canonical_url}"] = source_url
        if posting.posting_id:
            in_batch[f"id:{posting.site}:{posting.posting_id}"] = source_url
        new.append(
            NewJob(
                company_id=await store.company_id(company) if company else None,
                company_name=company or NO_COMPANY,
                title=facts.title,
                location_text=facts.location_text,
                city=facts.city,
                country=facts.country,
                work_mode=facts.work_mode,
                posted_at=facts.posted_at,
                description="",
                skills_found=facts.skills_found,
                years_found=None,
                canonical_url=facts.canonical_url,
                ats_vendor=posting.site,
                requisition_id=posting.posting_id,
                source_url=source_url,
                source_kind=SOURCE_KIND,
                injection_flags=_flags(posting.injection_signals),
                decision=decision,
                candidates=others,
                description_status="none",
                alert_read_by=posting.read_by,
            )
        )
        store.queue_sighting(source_url, sighting)

    counts = await store_batch(store, BatchWrite(search_run_id, batch_no, new, seen, [], 0, now))
    left_out = sum(
        1
        for job in new
        if job.decision.outcome == "skipped" and job.decision.rule_key != "already_in_pipeline"
    )
    return AlertCounts(
        new=counts.added,
        already_known=len(seen) - pipeline_again,
        left_out=left_out,
        already_in_pipeline=len(in_pipeline_titles) + pipeline_again,
        possible_duplicates=possible,
        in_pipeline_titles=tuple(in_pipeline_titles),
        progress=counts.progress,
    )
