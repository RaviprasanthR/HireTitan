"""T034: sanitizing untrusted resume text before anything else sees it (FR-006)."""

from __future__ import annotations

from hiretitan.platform.untrusted.sanitize import MAX_CHARS, sanitize


def test_FR006_control_and_zero_width_stripped() -> None:
    dirty = "Pyt​hon‍, Go\x00\x07 and⁠ SQL﻿­."
    assert sanitize(dirty).text == "Python, Go and SQL."


def test_bidi_controls_are_stripped() -> None:
    text = "name‮ evil‬ ⁦x⁩ ‏tail‎"
    assert sanitize(text).text == "name evil x tail"


def test_nfkc_normalizes_compatibility_characters() -> None:
    assert sanitize("Ｐython ﬁnance ½").text == "Python finance 1⁄2"  # noqa: RUF001 - compatibility characters are the input under test


def test_line_structure_kept() -> None:
    text = "EXPERIENCE\r\nAcme   Corp \t- Engineer  \r\n• Built    APIs\rSKILLS"
    assert sanitize(text).text == "EXPERIENCE\nAcme Corp - Engineer\n• Built APIs\nSKILLS"


def test_runs_of_blank_lines_collapse_to_one() -> None:
    assert sanitize("a\n\n\n\n\nb\n \n \nc").text == "a\n\nb\n\nc"


def test_leading_and_trailing_whitespace_removed() -> None:
    assert sanitize("\n\n  hello  \n\n").text == "hello"


def test_short_text_is_not_truncated() -> None:
    result = sanitize("short resume")
    assert result.truncated is None


def test_edge_case_long_resume_truncated_with_position() -> None:
    head = "EXPERIENCE\nAcme Corp\n"
    middle = "SKILLS\n" + ("Python, Go, SQL, Kafka\n" * 3000)
    result = sanitize(head + middle)

    assert len(result.text) == MAX_CHARS == 30_000
    assert result.truncated is not None
    assert result.truncated.offset == 30_000
    assert result.truncated.heading == "SKILLS"


def test_truncation_without_any_heading_reports_none() -> None:
    result = sanitize("plain text without headings " * 2000)
    assert result.truncated is not None
    assert result.truncated.heading is None


def test_truncation_counts_cleaned_characters_not_input_characters() -> None:
    # 40,000 zero-width characters add nothing once stripped.
    result = sanitize("​" * 40_000 + "hello")
    assert result.text == "hello"
    assert result.truncated is None


def test_title_case_section_names_count_as_headings() -> None:
    result = sanitize("Work Experience\n" + "x" * 40_000)
    assert result.truncated is not None
    assert result.truncated.heading == "Work Experience"


def test_empty_input() -> None:
    result = sanitize("")
    assert result.text == ""
    assert result.truncated is None
