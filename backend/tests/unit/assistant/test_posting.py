"""002m T012: a typed message that looks like a job posting is not sent to the AI (FR-021)."""

from __future__ import annotations

from hiretitan.assistant.domain.posting import looks_like_posting

POSTING = (
    "Backend Engineer at Acme\n\n"
    "About the role\n"
    + "You will build services that many teams depend on every day. " * 6
    + "\nResponsibilities:\n"
    + "- Design APIs and data models for new products.\n" * 4
    + "\nRequirements\n"
    + "- Five years of Python and PostgreSQL experience.\n" * 4
)


def test_FR021_posting_detected() -> None:
    assert len(POSTING) > 600
    assert looks_like_posting(POSTING) is True


def test_FR021_short_or_plain_messages_are_the_persons_own() -> None:
    assert looks_like_posting("I applied to the Acme backend job today.") is False
    assert looks_like_posting("Responsibilities:\nRequirements:\n") is False  # too short
    long_plain = "Can you tell me which jobs I applied to this month? " * 20
    assert looks_like_posting(long_plain) is False
    one_heading = "Requirements\n" + "Python and PostgreSQL. " * 40
    assert looks_like_posting(one_heading) is False
