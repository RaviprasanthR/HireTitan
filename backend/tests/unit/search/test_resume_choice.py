"""The resume choice on a pipeline job: how it is shown, and which files can be chosen (002f)."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from hiretitan.search.domain.resume_choice import ResumeChoice, choice_from, offerable

FILE_ID = uuid4()
ADDED = date(2026, 10, 2)


def test_display_rule_chosen() -> None:
    choice = choice_from(FILE_ID, "Backend_2025.pdf", ADDED)

    assert choice == ResumeChoice("chosen", FILE_ID, "Backend_2025.pdf", ADDED)


def test_display_rule_removed() -> None:
    # the file is gone (its id was cleared) but the name stays as a note
    choice = choice_from(None, "Backend_2024.pdf", ADDED)

    assert choice == ResumeChoice("removed", None, "Backend_2024.pdf", ADDED)


def test_display_rule_none() -> None:
    assert choice_from(None, None, None) == ResumeChoice("none", None, None, None)


def test_FR012_not_a_resume_is_not_offerable() -> None:
    assert not offerable("not_resume")


def test_FR012_files_still_being_read_or_failed_are_offerable() -> None:
    # the person uploaded these as resumes, so they can be chosen (spec edge case)
    for status in ("pending", "parsed", "no_text", "failed"):
        assert offerable(status), status
