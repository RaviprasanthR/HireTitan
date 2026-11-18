"""Recipient rules, tone rules and fallback templates (T010, T011, T016): FR-010 to FR-013."""

from __future__ import annotations

import pytest
from tests.fakes.drafts_data import TECH_TERMS, synthetic_profile

from hiretitan.drafts.domain.checks import check_length, check_text
from hiretitan.drafts.domain.facts import drafting_facts
from hiretitan.drafts.domain.fallback import connection_fallback, referral_fallback
from hiretitan.drafts.domain.recipient import (
    clean_typed,
    fill,
    first_name,
    kind_from_role,
    recipient_key,
    unknown_placeholders,
)
from hiretitan.drafts.domain.tone import check_tone

FACTS = drafting_facts(synthetic_profile())


@pytest.mark.parametrize(
    ("role", "kind"),
    [
        ("Talent Partner", "recruiter"),
        ("Senior Recruiter", "recruiter"),
        ("HR Business Partner", "recruiter"),
        ("Engineering Manager", "hiring_manager"),
        ("Head of Platform", "hiring_manager"),
        ("Staff Engineer", "engineer"),
        ("SDE II", "engineer"),
        ("Office Chef", "other"),
        (None, "other"),
        ("Shrmanager", "other"),
    ],
)
def test_FR010_kind_from_role(role: str | None, kind: str) -> None:
    assert kind_from_role(role) == kind


def test_FR013_first_name_only_no_invented_surname() -> None:
    assert first_name("Asha Rao") == "Asha"
    assert first_name("  Asha  ") == "Asha"
    assert first_name("") == ""


def test_EC02_typed_recipient_cleaned_and_bounded() -> None:
    typed = clean_typed("  Asha \x00 Rao ", "  Talent\tPartner ")
    assert (typed.name, typed.role) == ("Asha Rao", "Talent Partner")
    assert clean_typed("Asha", "   ").role is None
    with pytest.raises(ValueError):
        clean_typed("   ", None)
    with pytest.raises(ValueError):
        clean_typed("x" * 121, None)
    with pytest.raises(ValueError):
        clean_typed("Asha", "r" * 121)
    assert recipient_key(None, " ASHA  rao ") == "typed:asha rao"


def test_FR013_fill_replaces_only_known_placeholders() -> None:
    text = fill("Hi {recipient_first_name}, {other} {my_name}", "Asha", "Sam")
    assert text == "Hi Asha, {other} Sam"
    assert unknown_placeholders("Hi {recipient_first_name} {other} {my_name}") == ["{other}"]


@pytest.mark.parametrize("name_len", [1, 5, 60, 120])
@pytest.mark.parametrize("company", ["Acme", "A very long company name " * 4])
def test_US2_AS4_fallback_note_is_within_200_and_truthful(name_len: int, company: str) -> None:
    name = "N" * name_len
    template = connection_fallback("Backend Engineer", company, FACTS, name)
    text = fill(template, name, "Sam")
    assert not check_length(text, 200)
    found = check_text(
        template,
        (),
        FACTS,
        tech_terms=TECH_TERMS,
        allowed_names=(company,),
        years=7,
        context=f"Backend Engineer {company}",
    )
    assert found == []


def test_FR012_easy_decline_required() -> None:
    assert check_tone("I am interested in the role.", "")[0].code == "easy_out"
    assert check_tone("I am interested.", "No pressure at all.") == []


PUSHY = [
    "Please refer me by tomorrow.",
    "I need you to submit my resume.",
    "You must help me get this job.",
    "I'm counting on you.",
    "I'm the perfect fit for this.",
    "A referral is guaranteed to work.",
    "This is urgent.",
    "Reply ASAP please.",
    "You owe me a favour.",
    "Please forward my resume now.",
    "You have to refer me.",
    "You won't regret it.",
    "Respond by end of day.",
    "It is my last chance.",
    "Don't ignore this message.",
]


@pytest.mark.parametrize("body", PUSHY)
def test_FR012_pressure_phrases_rejected(body: str) -> None:
    codes = [p.code for p in check_tone(body, "No pressure at all.")]
    assert "pressure" in codes, body


@pytest.mark.parametrize(
    "body",
    [
        "I would value any advice about the team.",
        "If you have a minute, I would love to hear what the team is like.",
        "I admire the work on your platform.",
        "Happy to share my background if useful.",
        "I saw the opening and wanted to ask about it.",
    ],
)
def test_FR012_polite_examples_pass(body: str) -> None:
    assert check_tone(body, "Completely understand if it's not possible.") == []


def test_SC005_rules_are_case_insensitive() -> None:
    assert check_tone("PLEASE REPLY ASAP", "NO PRESSURE")[0].code == "pressure"
    assert [p.code for p in check_tone("You are the BEST and AMAZING", "No worries")] == [
        "flattery"
    ]


def test_FR012_referral_fallback_is_polite_and_truthful() -> None:
    parts = referral_fallback("Backend Engineer", "Acme", FACTS)
    text = parts.assemble()
    assert check_tone(parts.body, parts.easy_out) == []
    assert unknown_placeholders(text) == []
    found = check_text(
        text,
        (),
        FACTS,
        tech_terms=TECH_TERMS,
        allowed_names=("Acme",),
        years=7,
        context="Backend Engineer Acme",
    )
    assert found == []
    assert not check_length(fill(text, "Asha", "Sam"), 2000)
