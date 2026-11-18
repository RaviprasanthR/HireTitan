"""Facts and truthfulness checks (T008): FR-005, FR-022, SC-004. Synthetic data only."""

from __future__ import annotations

from datetime import date

import pytest
from tests.fakes.drafts_data import EXP_A, TECH_TERMS, synthetic_profile

from hiretitan.drafts.domain.checks import check_length, check_text
from hiretitan.drafts.domain.facts import drafting_facts, years_of_experience
from hiretitan.drafts.domain.profile_view import ExperienceView

TODAY = date(2026, 11, 17)
PROFILE = synthetic_profile()
FACTS = drafting_facts(PROFILE)
NAMES = ("Northwind Labs", "Initech Works", "Lakeside University", "Acme", "Budget Tracker")


def problems(
    text: str, cited: tuple[str, ...] = (), years: int | None = 7, context: str = ""
) -> list[str]:
    found = check_text(
        text,
        cited,
        FACTS,
        tech_terms=TECH_TERMS,
        allowed_names=NAMES,
        years=years,
        context=context,
    )
    return [p.code for p in found]


def test_FR022_facts_exclude_contact_details() -> None:
    joined = "\n".join(f.text for f in FACTS)
    for secret in ("sam.rivera", "555 0100", "example.invalid", "Sam Rivera", "Springfield"):
        assert secret not in joined


def test_FR005_years_of_experience_merges_overlaps() -> None:
    twice = ExperienceView(
        id="x", employer="Side Co", title="Freelance", start=(2022, 1), end=(2023, 1)
    )
    profile = PROFILE.__class__(contact=PROFILE.contact, experience=(*PROFILE.experience, twice))
    assert years_of_experience(PROFILE, TODAY) == years_of_experience(profile, TODAY)
    assert years_of_experience(PROFILE, TODAY) == 7  # 2019-01 .. 2026-11, no gap
    assert years_of_experience(PROFILE.__class__(contact=PROFILE.contact), TODAY) is None


def test_FR005_fabricated_number_rejected() -> None:
    assert "number" in problems("I cut costs by 73% last year.")
    assert problems("I built a service handling 40 requests per second.") == []


def test_FR005_years_claim_must_match_profile() -> None:
    assert "years" in problems("I have 9+ years of experience.", years=7)
    assert problems("I have 7+ years of experience.", years=7) == []
    assert "years" in problems("I have 3 years of experience.", years=None)


def test_FR005_unknown_tech_rejected() -> None:
    assert "technology" in problems("I work with Kubernetes daily.")
    assert problems("I work with Python and Django.") == []
    assert problems("I am curious about Rust.", context="Rust Engineer") == []
    # the job's title may name a technology, but it cannot vouch for the person using it
    title = "Kubernetes Platform Engineer"
    assert "technology" in problems("I have worked with Kubernetes for years.", context=title)
    assert "technology" in problems("I am experienced in building on Kubernetes.", context=title)
    assert problems("The Kubernetes Platform Engineer role caught my eye.", context=title) == []


def test_FR005_unknown_organisation_rejected() -> None:
    assert "name" in problems("I spent time at Globex before.")
    assert problems("I spent time at Northwind Labs before.") == []
    assert problems("I am keen on the role at Acme.") == []


def test_FR005_sentence_start_capital_is_not_a_name() -> None:
    assert problems("Reliable APIs are my focus. Testing matters to me.") == []


def test_FR005_cited_id_must_exist() -> None:
    assert problems("Hello there.", cited=("skill:python",)) == []
    assert "unknown_fact" in problems("Hello there.", cited=("skill:cobol",))


def test_FR005_placeholders_are_ignored() -> None:
    assert problems("Hi {recipient_first_name}, thanks. {my_name}") == []


def test_FR011_check_length() -> None:
    assert check_length("a" * 200, 200) == []
    assert check_length("a" * 201, 200)[0].code == "too_long"


SEEDED = [
    "I led a team of 12 engineers.",
    "I increased revenue by 47%.",
    "I have 15 years of experience.",
    "I am an expert in Kubernetes.",
    "I worked at Globex on payments.",
    "I used Java every day.",
    "I hold a certification from Hooli.",
    "I studied at Stanford.",
    "I shipped 5 products in 2018.",
    "I am a Principal Architect at Umbrella.",
    "I saved 2 million dollars.",
    "I mentored 8 juniors.",
    "I moved everything to K8s.",
    "I ran Rust services in production at Wayne.",
    "I managed a 30 person group.",
    "I built it for Wonka.",
    "I cut latency by 90 percent.",
    "I am a Staff Engineer at Cyberdyne.",
    "I earned an MBA at Oxford.",
    "I handled 1000 tickets weekly.",
]


@pytest.mark.parametrize("text", SEEDED)
def test_SC004_seeded_fabrications_all_caught(text: str) -> None:
    assert problems(text, years=7), text


def test_SC004_a_true_statement_passes() -> None:
    text = "I build Python APIs at Northwind Labs and moved a PostgreSQL schema to partitions."
    assert problems(text, cited=(f"{EXP_A}:role", "skill:python")) == []
