"""Matching a sheet row to a company on the list (feature 002b, T010; FR-003; research R4)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from hiretitan.search.domain.company_match import (
    Ambiguous,
    CompanyRef,
    Matched,
    NoMatch,
    match,
    name_match_key,
    website_key,
)


def _ref(name: str, website: str | None = None) -> CompanyRef:
    return CompanyRef(uuid4(), name, website)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.acme.example.test/",
        "http://acme.example.test",
        "acme.example.test/careers/jobs?x=1",
        "HTTPS://ACME.EXAMPLE.TEST",
        "www.acme.example.test",
    ],
)
def test_FR003_website_ignores_www_scheme_and_trailing_slash(url: str) -> None:
    assert website_key(url) == "acme.example.test"


@pytest.mark.parametrize("url", [None, "", "   ", "not a site", "https://"])
def test_FR003_no_website_key_without_a_host(url: str | None) -> None:
    assert website_key(url) is None


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Example Beta", "example   beta"),
        ("Example Beta", "Example-Beta!"),
        ("Example Beta", "Example Beta Inc."),
        ("Example Beta", "Example Beta Pvt. Ltd."),
        ("Example Beta", "Example Beta Technologies LLC"),
        ("Café Example", "Cafe Example"),
    ],
)
def test_FR003_name_ignores_case_spacing_punctuation_and_suffix(a: str, b: str) -> None:
    assert name_match_key(a) == name_match_key(b)


def test_FR003_a_name_that_is_only_a_suffix_keeps_it() -> None:
    assert name_match_key("Technologies") == "technologies"


def test_FR003_different_names_differ() -> None:
    assert name_match_key("Example Beta") != name_match_key("Example Gamma")


def test_FR003_website_match_beats_name_match() -> None:
    plain = _ref("Acme", "https://acme.example.test")
    inc = _ref("Acme Labs Inc", "https://acme-labs.example.test")
    same_name = _ref("Acme", "https://other.example.test")

    result = match("Acme", "https://www.acme.example.test/", [plain, inc, same_name])

    assert result == Matched(plain.id)


def test_FR003_name_match_when_the_row_has_no_website() -> None:
    beta = _ref("Example Beta", "https://beta.example.test")
    alpha = _ref("Example Alpha", "https://alpha.example.test")

    assert match("Example Beta Inc.", None, [alpha, beta]) == Matched(beta.id)


def test_FR003_website_match_when_the_name_differs() -> None:
    alpha = _ref("Example Alpha", "https://alpha.example.test")

    assert match("Alpha Renamed", "alpha.example.test", [alpha]) == Matched(alpha.id)


def test_US1_AS4_two_matches_are_ambiguous() -> None:
    alpha = _ref("Example Alpha", "https://alpha.example.test")
    beta = _ref("Example Beta", "https://beta.example.test")

    result = match("Example Beta", "https://alpha.example.test", [beta, alpha])

    assert result == Ambiguous(("Example Alpha", "Example Beta"))


def test_US1_AS4_two_companies_with_one_name_are_ambiguous() -> None:
    first = _ref("Acme", "https://one.example.test")
    second = _ref("Acme Inc", "https://two.example.test")

    result = match("Acme", None, [first, second])

    assert result == Ambiguous(("Acme", "Acme Inc"))


def test_edge_subdomain_is_not_the_same_website() -> None:
    acme = _ref("Acme", "https://acme.example.test")

    assert match("Other Name", "https://careers.acme.example.test", [acme]) == NoMatch()


def test_US1_AS2_no_match_is_no_match() -> None:
    acme = _ref("Acme", "https://acme.example.test")

    assert match("Sample Delta", "https://delta.example.test", [acme]) == NoMatch()
    assert match("Sample Delta", None, []) == NoMatch()


def test_edge_company_ids_are_returned_as_uuids() -> None:
    acme = _ref("Acme")
    result = match("Acme", None, [acme])

    assert isinstance(result, Matched)
    assert isinstance(result.company_id, UUID)
