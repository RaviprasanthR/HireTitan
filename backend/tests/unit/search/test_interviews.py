"""Interview tracking rules: pure checks, numbering and the status column (feature 002e)."""

from __future__ import annotations

from hiretitan.search.domain.interviews import (
    ANSWER_MAX,
    FEEDBACK_MAX,
    INTERVIEWERS_MAX,
    QUESTION_MAX,
    RoundSummary,
    can_add_round,
    check_contact,
    check_round_text,
    check_source,
    next_round_number,
    status_summary,
)


def test_FR004_next_round_number() -> None:
    assert next_round_number([]) == 1
    assert next_round_number([1, 2]) == 3
    assert next_round_number([1, 3]) == 4  # a gap is not refilled while a higher number exists
    assert next_round_number([1, 2]) == 3  # deleting round 3 means the next one is round 3 again


def test_FR006_failed_blocks_new_rounds() -> None:
    assert can_add_round([])
    assert can_add_round(["cleared", "scheduled"])
    assert not can_add_round(["cleared", "failed"])


def test_FR007_status_summary_no_rounds() -> None:
    assert status_summary("applied", []) == ("applied", None)
    assert status_summary("inquired", []) == ("inquired", None)


def test_FR007_status_summary_latest_round() -> None:
    rounds = [RoundSummary(1, "cleared"), RoundSummary(2, "scheduled")]

    assert status_summary("applied", rounds) == ("scheduled", 2)
    assert status_summary("applied", [RoundSummary(1, "cleared")]) == ("cleared", 1)


def test_FR007_status_summary_follows_round_number_not_list_order() -> None:
    rounds = [RoundSummary(3, "scheduled"), RoundSummary(1, "cleared")]

    assert status_summary("applied", rounds) == ("scheduled", 3)


def test_FR007_status_summary_failed_wins() -> None:
    rounds = [
        RoundSummary(1, "cleared"),
        RoundSummary(2, "failed"),
        RoundSummary(3, "scheduled"),  # a later round does not hide the failure
    ]

    assert status_summary("applied", rounds) == ("failed", 2)


def test_FR007_status_summary_highest_failed_round() -> None:
    rounds = [RoundSummary(1, "failed"), RoundSummary(2, "cleared"), RoundSummary(3, "failed")]

    assert status_summary("inquired", rounds) == ("failed", 3)


def test_FR003_hiring_firm_needs_a_name() -> None:
    value, issues = check_source("hiring_firm", "  ")

    assert value is None
    assert [i.field for i in issues] == ["firm_name"]


def test_FR003_source_values() -> None:
    assert check_source("hiring_firm", " TalentBridge ")[0] == ("hiring_firm", "TalentBridge")
    assert check_source("direct", "Ignored Ltd")[0] == ("direct", None)  # a firm only with a firm
    assert check_source(None, "x")[0] == (None, None)
    value, issues = check_source("agency", None)
    assert value is None
    assert [i.field for i in issues] == ["kind"]


def test_FR003_firm_name_limit() -> None:
    _, issues = check_source("hiring_firm", "x" * 121)

    assert [i.field for i in issues] == ["firm_name"]


def test_FR002_contact_checks() -> None:
    fields, issues = check_contact(name="Asha Rao")
    assert issues == []
    assert fields is not None
    assert fields.name == "Asha Rao"
    assert fields.email is None

    _, issues = check_contact(name="", email="not-an-email", linkedin_url="nope", phone="x")
    assert {i.field for i in issues} == {"name", "email", "linkedin_url", "phone"}


def test_FR002_contact_keeps_optional_fields() -> None:
    fields, issues = check_contact(
        name="Asha",
        role="Recruiter",
        email="asha@example.com",
        phone="+91 98765 43210",
        linkedin_url="linkedin.com/in/asha",
    )

    assert issues == []
    assert fields is not None
    assert fields.linkedin_url == "https://linkedin.com/in/asha"
    assert fields.role == "Recruiter"


def test_FR014_line_breaks_kept() -> None:
    text, issues = check_round_text("feedback", "First paragraph.\n\nSecond one.", FEEDBACK_MAX)

    assert issues == []
    assert text == "First paragraph.\n\nSecond one."


def test_FR014_empty_text_is_none_and_long_text_is_refused_with_the_limit() -> None:
    assert check_round_text("feedback", "   ", FEEDBACK_MAX) == (None, [])
    text, issues = check_round_text("question", "q" * (QUESTION_MAX + 1), QUESTION_MAX)
    assert text is None
    assert [i.field for i in issues] == ["question"]
    assert str(QUESTION_MAX) in issues[0].message


def test_limits_match_the_data_model() -> None:
    assert (INTERVIEWERS_MAX, QUESTION_MAX, ANSWER_MAX, FEEDBACK_MAX) == (300, 2000, 10000, 10000)
