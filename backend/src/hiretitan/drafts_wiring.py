"""Adapters that answer the drafts module's questions from the profile and search modules.

The drafts module may not import other features, so this composition-level file (allowed to see
every module) reads the confirmed profile, the jobs and the company contacts for it, and gives
``search`` the job clean-up it calls when a job is deleted (feature 002k).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.drafts.application.ports import (
    ConfirmedProfile,
    ContactInfo,
    JobInfo,
)
from hiretitan.drafts.domain.checks import TechTerms
from hiretitan.drafts.domain.profile_view import (
    CertificationView,
    ContactView,
    EducationView,
    ExperienceView,
    ProfileView,
    ProjectView,
    YearMonth,
)
from hiretitan.drafts.infra.repos import DraftsRepo, KeywordsRepo, TailoredRepo
from hiretitan.profile.domain.content import ProfileContent
from hiretitan.profile.domain.content import YearMonth as ProfileYearMonth
from hiretitan.profile.infra.repos import VersionsRepo
from hiretitan.search.domain.tech_names import TechTable
from hiretitan.search.infra.repos import ContactsRepo, JobsRepo


def _ym(value: ProfileYearMonth | None) -> YearMonth | None:
    return None if value is None else (value.year, value.month)


def profile_view(content: ProfileContent) -> ProfileView:
    """The confirmed profile as the plain values the drafts module works with."""
    contact = content.contact
    return ProfileView(
        contact=ContactView(
            name=contact.name,
            email=contact.email,
            phone=contact.phone,
            location=contact.location,
            links=tuple(link.url for link in contact.links),
        ),
        headline=content.headline,
        summary=content.summary,
        experience=tuple(
            ExperienceView(
                id=str(job.id),
                employer=job.employer,
                title=job.title,
                start=_ym(job.start),
                end=_ym(job.end),
                current=job.current,
                location=job.location,
                bullets=job.bullets,
            )
            for job in content.experience
        ),
        education=tuple(
            EducationView(
                id=str(edu.id),
                institution=edu.institution,
                qualification=edu.qualification,
                field_of_study=edu.field_of_study,
                start=_ym(edu.start),
                end=_ym(edu.end),
            )
            for edu in content.education
        ),
        skills=content.skills,
        projects=tuple(
            ProjectView(
                id=str(project.id),
                name=project.name,
                description=project.description,
                technologies=project.technologies,
            )
            for project in content.projects
        ),
        certifications=tuple(
            CertificationView(
                id=str(cert.id), name=cert.name, issuer=cert.issuer, date=_ym(cert.date)
            )
            for cert in content.certifications
        ),
    )


def tech_terms(table: TechTable) -> TechTerms:
    """Technology names the checks watch for. Ordinary words that need a context word (``Go``)
    are left out: they cannot be told from plain English."""
    return tuple((tech.name, tech.aliases) for tech in table if not tech.context)


class SqlProfileFacts:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def current(self) -> ConfirmedProfile | None:
        async with self._sessions() as session:
            version = await VersionsRepo(session).current()
        if version is None:
            return None
        return ConfirmedProfile(version.id, profile_view(version.content))


class SqlJobs:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, job_id: UUID) -> JobInfo | None:
        async with self._sessions() as session:
            row = await JobsRepo(session).get(job_id)
        if row is None or row.state == "deleted":
            return None
        return JobInfo(
            id=row.id,
            title=row.title,
            company_name=row.company_name,
            company_id=row.company_id,
            description=row.description,
            state=row.state,
        )


class SqlContacts:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def for_company(self, company_id: UUID) -> list[ContactInfo]:
        async with self._sessions() as session:
            rows = await ContactsRepo(session).list_for_company(company_id)
        return [ContactInfo(r.id, r.company_id, r.name, r.role) for r in rows]

    async def get(self, contact_id: UUID) -> ContactInfo | None:
        async with self._sessions() as session:
            row = await ContactsRepo(session).get(contact_id)
        return None if row is None else ContactInfo(row.id, row.company_id, row.name, row.role)


async def clear_drafts_for_job(session: AsyncSession, job_id: UUID) -> None:
    """Everything the drafts module holds about a job goes with it (spec FR-009)."""
    await KeywordsRepo(session).clear_for_job(job_id)
    await DraftsRepo(session).clear_for_job(job_id)
    await TailoredRepo(session).clear_for_job(job_id)
