"""The rule-based short role: it only removes words from the title (Applied table)."""

from __future__ import annotations

import pytest

from hiretitan.prompts.judge_relevance.v2.checks import role_words_outside
from hiretitan.search.domain.role import ROLE_MAX, short_role


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior Backend Engineer (Python) - Remote - Pune", "Senior Backend Engineer"),
        ("Backend Engineer | Req 48213", "Backend Engineer"),
        ("Data Analyst [Hybrid]", "Data Analyst"),
        ("Software Engineer, Backend", "Software Engineer, Backend"),
        ("Engineer II " + chr(0x2013) + " Payments Platform", "Engineer II"),
        ("Product Manager #R-9921", "Product Manager"),
        ("Frontend Developer", "Frontend Developer"),
        ("(Remote) - Pune", "(Remote) - Pune"),  # nothing left: keep the title
    ],
)
def test_short_role_cuts_extras(title: str, expected: str) -> None:
    assert short_role(title) == expected


def test_short_role_is_capped_at_a_word() -> None:
    title = "Principal Distributed Systems Reliability Engineering Manager for Global Platforms"
    result = short_role(title)
    assert len(result) <= ROLE_MAX
    assert result.endswith("…")
    assert not role_words_outside(result.rstrip("…"), title)


@pytest.mark.parametrize(
    "title",
    ["Senior Backend Engineer (Python) - Remote - Pune", "Backend Engineer | Req 48213"],
)
def test_short_role_adds_no_words(title: str) -> None:
    assert not role_words_outside(short_role(title), title)
