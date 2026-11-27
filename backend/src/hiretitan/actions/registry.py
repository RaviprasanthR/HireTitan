"""Build the one catalogue of Mikasa's actions (002m research R3)."""

from __future__ import annotations

from hiretitan.actions import (
    companies,
    company_changes,
    contacts,
    drafts,
    interview_changes,
    interviews,
    job_changes,
    jobs,
    mail,
    profile,
    risky_companies,
    risky_jobs,
    risky_profile,
    search,
    settings,
)
from hiretitan.actions.catalogue import Catalogue


def build_catalogue() -> Catalogue:
    catalogue = Catalogue()
    for spec in (
        *jobs.READS,
        *search.READS,
        *mail.READS,
        *companies.READS,
        *contacts.READS,
        *interviews.READS,
        *drafts.READS,
        *profile.READS,
        *settings.READS,
        *job_changes.CHANGES,
        *company_changes.CHANGES,
        *interview_changes.CHANGES,
        *risky_jobs.CHANGES,
        *risky_companies.CHANGES,
        *risky_profile.CHANGES,
        *drafts.CHANGES,
    ):
        catalogue.register(spec)
    return catalogue
