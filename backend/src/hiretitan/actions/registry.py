"""Build the one catalogue of Mikasa's actions (002m research R3)."""

from __future__ import annotations

from hiretitan.actions import (
    companies,
    contacts,
    interviews,
    jobs,
    mail,
    profile,
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
        *profile.READS,
        *settings.READS,
    ):
        catalogue.register(spec)
    return catalogue
