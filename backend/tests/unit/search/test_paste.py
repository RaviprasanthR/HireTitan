"""002m T019: a job can be added with its link, title and company only (research R12), so Mikasa
can add a job from a link without HireTitan ever opening the link."""

from __future__ import annotations

import pytest

from hiretitan.search.application.paste import PasteError, PasteInput, _check


def fields(error: PasteError) -> set[str]:
    return {issue.field for issue in error.errors}


def test_R12_link_only_needs_title_and_company() -> None:
    url, description, title, company = _check(
        PasteInput(
            url="https://jobs.example.com/acme/1",
            description="",
            title="Backend Engineer",
            company="Acme",
            link_only=True,
        )
    )
    assert (url, description, title, company) == (
        "https://jobs.example.com/acme/1",
        "",
        "Backend Engineer",
        "Acme",
    )

    with pytest.raises(PasteError) as caught:
        _check(PasteInput(url="https://jobs.example.com/acme/1", description="", link_only=True))
    assert fields(caught.value) == {"title", "company"}


def test_R12_without_link_only_a_description_is_still_required() -> None:
    with pytest.raises(PasteError) as caught:
        _check(
            PasteInput(
                url="https://jobs.example.com/acme/1",
                description="",
                title="Backend Engineer",
                company="Acme",
            )
        )
    assert fields(caught.value) == {"description"}


def test_R12_link_only_with_a_short_description_keeps_the_description_rules() -> None:
    with pytest.raises(PasteError) as caught:
        _check(
            PasteInput(
                url="https://jobs.example.com/acme/1",
                description="too short",
                title="Backend Engineer",
                company="Acme",
                link_only=True,
            )
        )
    assert fields(caught.value) == {"description"}
