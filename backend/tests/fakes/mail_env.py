"""Helpers for mail tests: a search run in the mail mode and a job to attach sightings to."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.search.infra.repos import CompaniesRepo, JobsRepo, RuleSetsRepo, SearchRunsRepo

NOW = datetime(2026, 11, 18, 9, tzinfo=UTC)


async def make_run(session: AsyncSession, mode: str = "mail_alerts") -> UUID:
    rules = RuleSetsRepo(session)
    rule_set = await rules.approve((await rules.propose({}, {})).id)
    workflow = await RunsRepo(session).create("mail_check")
    run = await SearchRunsRepo(session).create(
        workflow_run_id=workflow.id, rule_set_id=rule_set.id, mode=mode, company_order=[]
    )
    return run.id


async def make_job(session: AsyncSession, title: str = "Backend Engineer") -> UUID:
    company = await CompaniesRepo(session).add(
        name=f"Acme {title}", origin="user", resolution="verified"
    )
    job = await JobsRepo(session).add(
        company_id=company.id,
        company_name=company.name,
        title=title,
        first_seen_at=NOW,
        last_seen_at=NOW,
        description="",
        state="explore",
    )
    return job.id
