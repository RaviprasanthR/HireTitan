"""Contact field checks and identity keys (feature 002b, FR-006, FR-009, FR-012, R11)."""

from __future__ import annotations

import pytest

from hiretitan.search.domain.contacts import (
    check_company_note,
    check_contact,
    link_key,
    name_key,
)


def _fields(**kw: str | None) -> dict[str, str | None]:
    return {"name": "Jane Example", **kw}


def test_FR009_only_name_is_required() -> None:
    fields, issues = check_contact(name="Jane Example")

    assert issues == []
    assert fields is not None
    assert fields.name == "Jane Example"
    assert fields.role is None
    assert fields.linkedin_url is None
    assert fields.email is None
    assert fields.phone is None
    assert fields.confidence is None
    assert fields.note is None


@pytest.mark.parametrize("name", ["", "   ", None])
def test_FR009_missing_name_is_an_error(name: str | None) -> None:
    fields, issues = check_contact(name=name)

    assert fields is None
    assert [i.field for i in issues] == ["name"]


def test_FR009_name_over_120_is_an_error() -> None:
    _, issues = check_contact(name="x" * 121)

    assert [i.field for i in issues] == ["name"]


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("https://www.linkedin.com/in/jane-example", "https://www.linkedin.com/in/jane-example"),
        ("http://linkedin.com/in/jane", "http://linkedin.com/in/jane"),
        ("linkedin.com/in/jane-example", "https://linkedin.com/in/jane-example"),
        ("www.linkedin.com/in/jane", "https://www.linkedin.com/in/jane"),
    ],
)
def test_FR012_link_is_stored_with_a_scheme(raw: str, stored: str) -> None:
    fields, issues = check_contact(name="Jane", linkedin_url=raw)

    assert issues == []
    assert fields is not None
    assert fields.linkedin_url == stored


@pytest.mark.parametrize(
    "raw",
    [
        "javascript:alert(1)",
        "not a link",
        "https://",
        "ftp://linkedin.com/in/x",
        "https:///in/x",
        "data:text/html,hi",
        "https://" + "a" * 500 + ".com",
    ],
)
def test_FR012_link_must_be_http_or_https(raw: str) -> None:
    fields, issues = check_contact(name="Jane", linkedin_url=raw)

    assert fields is None
    assert [i.field for i in issues] == ["linkedin_url"]


@pytest.mark.parametrize("raw", ["jane@example.com", "a.b+c@sub.example.co.in"])
def test_FR012_email_and_phone_shapes_accepted(raw: str) -> None:
    fields, issues = check_contact(name="Jane", email=raw, phone="+91 98765-43210")

    assert issues == []
    assert fields is not None
    assert fields.email == raw
    assert fields.phone == "+91 98765-43210"


@pytest.mark.parametrize(
    "raw", ["jane", "jane@", "@example.com", "jane@example", "a b@example.com"]
)
def test_FR012_bad_email_is_refused(raw: str) -> None:
    _, issues = check_contact(name="Jane", email=raw)

    assert [i.field for i in issues] == ["email"]


@pytest.mark.parametrize("raw", ["1234", "call me", "1" * 31, "12345abc"])
def test_FR012_bad_phone_is_refused(raw: str) -> None:
    _, issues = check_contact(name="Jane", phone=raw)

    assert [i.field for i in issues] == ["phone"]


def test_R11_every_bad_field_is_reported_together() -> None:
    fields, issues = check_contact(
        name="Jane", linkedin_url="nope nope", email="x", phone="1", confidence="maybe"
    )

    assert fields is None
    assert [i.field for i in issues] == ["linkedin_url", "email", "phone", "confidence"]


@pytest.mark.parametrize("value", ["high", "medium", "low", "HIGH", " Low "])
def test_FR009_confidence_values(value: str) -> None:
    fields, issues = check_contact(name="Jane", confidence=value)

    assert issues == []
    assert fields is not None
    assert fields.confidence == value.strip().lower()


def test_FR009_length_limits_on_role_and_note() -> None:
    _, issues = check_contact(name="Jane", role="r" * 121, note="n" * 2001)

    assert [i.field for i in issues] == ["role", "note"]
    ok, none = check_contact(name="Jane", role="r" * 120, note="n" * 2000)
    assert none == []
    assert ok is not None


def test_FR026_control_characters_are_stripped_and_empty_text_is_none() -> None:
    fields, issues = check_contact(name="Ja\x00ne​", role="  ", note="a\x07b")

    assert issues == []
    assert fields is not None
    assert fields.name == "Jane"
    assert fields.role is None
    assert fields.note == "ab"


def test_FR010_company_note_limit_and_empty() -> None:
    assert check_company_note("  ") == (None, [])
    body, issues = check_company_note("Spoke to HR on Monday.")
    assert (body, issues) == ("Spoke to HR on Monday.", [])
    none, issues = check_company_note("n" * 5001)
    assert none is None
    assert [i.field for i in issues] == ["body"]


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Jane Example", "jane   example"),
        ("Jane Example", "JANE EXAMPLE"),
        ("Jane Example", "Jane. Example,"),
        ("José Example", "Jose Example"),
        ("José Example", "José Example"),
    ],
)
def test_FR006_name_key_ignores_case_spacing_punctuation_accents(a: str, b: str) -> None:
    assert name_key(a) == name_key(b)
    assert name_key(a) != ""


def test_FR006_different_people_have_different_keys() -> None:
    assert name_key("Jane Example") != name_key("Jane Sample")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/in/jane-example/",
        "http://linkedin.com/in/Jane-Example?utm=1#top",
        "linkedin.com/in/jane-example",
        "HTTPS://WWW.LINKEDIN.COM/IN/JANE-EXAMPLE",
    ],
)
def test_FR006_link_key_drops_scheme_www_query_fragment_trailing_slash(url: str) -> None:
    assert link_key(url) == "linkedin.com/in/jane-example"


def test_FR006_link_key_is_none_without_a_link() -> None:
    assert link_key(None) is None
    assert link_key("") is None
