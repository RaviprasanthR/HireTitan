"""A drafts test environment: a confirmed synthetic profile, a company with contacts, a job, and a
scripted fake LLM. Contacts carry distinctive synthetic details so a privacy test can look for them
in every recorded request."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan import prompts as hiretitan_prompts
from hiretitan.drafts.workflow.common import DraftDeps
from hiretitan.drafts_wiring import SqlJobs, SqlProfileFacts, tech_terms
from hiretitan.platform.clock import FakeClock
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.profile.domain.content import (
    Certification,
    Contact,
    Education,
    Experience,
    Link,
    ProfileContent,
    Project,
    YearMonth,
)
from hiretitan.profile.infra.repos import VersionsRepo
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.domain.tech_names import TechName
from hiretitan.search.infra.repos import CompaniesRepo, ContactsRepo, JobsRepo

NOW = datetime(2026, 11, 17, 9, tzinfo=UTC)
MY_NAME = "Sam Rivera"
MY_EMAIL = "sam.rivera.private@example.invalid"
MY_PHONE = "+1 555 0142"
MY_LINK = "https://example.invalid/in/sam-rivera-private"
CONTACT_NAME = "Quillon Fairweather"
CONTACT_ROLE = "Talent Partner"
CONTACT_EMAIL = "quillon.fairweather@example.invalid"
CONTACT_LINK = "https://example.invalid/in/quillon-fairweather"
CONTACT_NOTE = "Met at a meetup about distinctive-note-9731"
DESCRIPTION = (
    "We are hiring a Backend Engineer to build Python APIs on PostgreSQL. "
    "You will design services, review code and run them in production. "
    "Required: Python, PostgreSQL, REST design. Nice to have: Django. " * 2
)
TECH = (
    TechName("Python", "language", ()),
    TechName("Java", "language", ()),
    TechName("Kubernetes", "framework", ("k8s",)),
    TechName("PostgreSQL", "framework", ("postgres",)),
    TechName("Django", "framework", ()),
)


def synthetic_content() -> ProfileContent:
    return ProfileContent(
        contact=Contact(
            name=MY_NAME,
            email=MY_EMAIL,
            phone=MY_PHONE,
            location="Springfield",
            links=(Link(MY_LINK),),
        ),
        headline="Backend engineer",
        summary="Backend engineer who builds reliable APIs in Python.",
        experience=(
            Experience(
                employer="Northwind Labs",
                title="Backend Engineer",
                start=YearMonth(2021, 3),
                current=True,
                bullets=(
                    "Built a Python service handling 40 requests per second",
                    "Moved a PostgreSQL schema to partitioned tables",
                ),
            ),
            Experience(
                employer="Initech Works",
                title="Junior Developer",
                start=YearMonth(2019, 1),
                end=YearMonth(2021, 2),
                bullets=("Wrote Django views and tests",),
            ),
        ),
        education=(
            Education(
                institution="Lakeside University",
                qualification="BSc",
                field_of_study="Computer Science",
                start=YearMonth(2015),
                end=YearMonth(2019),
            ),
        ),
        skills=("Python", "PostgreSQL", "Django"),
        projects=(Project(name="Budget Tracker", description="A small expense tracker"),),
        certifications=(Certification(name="Cloud Basics", issuer="Skillhub"),),
    )


@dataclass
class DraftsEnv:
    sessions: async_sessionmaker[AsyncSession]
    llm: FakeLlm
    deps: DraftDeps
    job_id: UUID
    company_id: UUID
    contact_id: UUID
    published: list[tuple[str, dict[str, Any]]]


async def make_env(
    sessions: async_sessionmaker[AsyncSession],
    *,
    with_profile: bool = True,
    description: str = DESCRIPTION,
    title: str = "Backend Engineer",
) -> DraftsEnv:
    async with sessions() as session:
        if with_profile:
            await VersionsRepo(session).create_version(synthetic_content(), created_by="manual")
        company = await CompaniesRepo(session).add(
            name="Acme", origin="user", resolution="verified"
        )
        contact = await ContactsRepo(session).add(
            company.id,
            ContactFields(
                name=CONTACT_NAME,
                role=CONTACT_ROLE,
                linkedin_url=CONTACT_LINK,
                email=CONTACT_EMAIL,
                note=CONTACT_NOTE,
            ),
            source="typed",
        )
        job = await JobsRepo(session).add(
            company_id=company.id,
            company_name="Acme",
            title=title,
            first_seen_at=NOW,
            last_seen_at=NOW,
            description=description,
            state="explore",
        )
        await session.commit()
        ids = (job.id, company.id, contact.id)
    published: list[tuple[str, dict[str, Any]]] = []

    async def publish(event: str, data: dict[str, Any]) -> None:
        published.append((event, data))

    llm = FakeLlm()
    deps = DraftDeps(
        sessions=sessions,
        llm=llm,
        prompts=PromptRegistry(Path(hiretitan_prompts.__file__).parent),
        profile=SqlProfileFacts(sessions),
        jobs=SqlJobs(sessions),
        clock=FakeClock(NOW),
        publish=publish,
        tech_terms=tech_terms(TECH),
        provider="fake",
    )
    return DraftsEnv(sessions, llm, deps, ids[0], ids[1], ids[2], published)


KEYWORDS = {
    "role_summary": "Backend engineer building Python APIs on PostgreSQL.",
    "keywords": ["Python", "PostgreSQL", "REST", "Django"],
    "must_have": ["Python", "PostgreSQL"],
}
GOOD_CONNECTION = {
    "body": (
        "Hi {recipient_first_name}, I build Python APIs and am interested in the Backend "
        "Engineer role at Acme. Happy to connect."
    ),
    "cited_fact_ids": ["skill:python"],
}
