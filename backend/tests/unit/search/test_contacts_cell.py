"""The contacts cell of a company sheet (feature 002b, T009; FR-005, FR-024; research R3)."""

from __future__ import annotations

import itertools

import pytest

from hiretitan.search.domain.contacts_cell import ParsedContact, parse, render


def test_US1_AS3_one_contact_per_person_with_role_tag_and_link() -> None:
    cell = (
        "Jane Example - Recruiter [High]\n"
        "https://www.linkedin.com/in/jane-example\n"
        "John Sample - Engineering Manager [Med]\n"
        "https://www.linkedin.com/in/john-sample\n"
        "Asha Demo - HR [Low]"
    )

    parsed = parse(cell)

    assert [(c.name, c.role, c.confidence, c.linkedin_url) for c in parsed.contacts] == [
        ("Jane Example", "Recruiter", "high", "https://www.linkedin.com/in/jane-example"),
        ("John Sample", "Engineering Manager", "medium", "https://www.linkedin.com/in/john-sample"),
        ("Asha Demo", "HR", "low", None),
    ]
    assert parsed.leftover == ()
    assert parsed.shortened is False


@pytest.mark.parametrize(
    ("tag", "confidence"),
    [
        ("[High]", "high"),
        ("[Med]", "medium"),
        ("[Medium]", "medium"),
        ("[Low]", "low"),
        ("[HIGH]", "high"),
        ("[ med ]", "medium"),
    ],
)
def test_FR005_confidence_tags_high_med_medium_low(tag: str, confidence: str) -> None:
    parsed = parse(f"Jane Example - Recruiter {tag}")

    assert parsed.contacts[0].confidence == confidence
    assert parsed.contacts[0].name == "Jane Example"
    assert parsed.contacts[0].role == "Recruiter"


def test_FR005_tag_may_sit_anywhere_on_the_line() -> None:
    parsed = parse("[High] Jane Example, Recruiter")

    assert (parsed.contacts[0].name, parsed.contacts[0].role) == ("Jane Example", "Recruiter")
    assert parsed.contacts[0].confidence == "high"


@pytest.mark.parametrize(
    "line",
    [
        "Jane Example - Recruiter",
        "Jane Example – Recruiter",  # noqa: RUF001
        "Jane Example — Recruiter",
        "Jane Example, Recruiter",
        "Jane Example (Recruiter)",
    ],
)
def test_FR005_role_separators(line: str) -> None:
    parsed = parse(line)

    assert (parsed.contacts[0].name, parsed.contacts[0].role) == ("Jane Example", "Recruiter")


def test_FR005_unplaceable_text_is_kept_as_a_note() -> None:
    cell = (
        "Jane Example - Recruiter\n"
        "Prefers a short message, replies within a day.\n"
        "https://www.linkedin.com/in/jane-example"
    )

    parsed = parse(cell)

    assert len(parsed.contacts) == 1
    assert parsed.contacts[0].note == "Prefers a short message, replies within a day."
    assert parsed.contacts[0].linkedin_url == "https://www.linkedin.com/in/jane-example"


def test_FR005_cell_without_a_person_becomes_a_company_note() -> None:
    parsed = parse("no LinkedIn URL found - name via RocketReach")

    assert parsed.contacts == ()
    assert parsed.leftover == ("no LinkedIn URL found - name via RocketReach",)


def test_edge_url_line_without_person_is_leftover() -> None:
    parsed = parse("https://www.linkedin.com/company/example-co\nJane Example - HR")

    assert parsed.leftover == ("https://www.linkedin.com/company/example-co",)
    assert [c.name for c in parsed.contacts] == ["Jane Example"]
    assert parsed.contacts[0].linkedin_url is None


def test_edge_bare_linkedin_link_gets_a_scheme() -> None:
    parsed = parse("Jane Example\nlinkedin.com/in/jane-example")

    assert parsed.contacts[0].linkedin_url == "https://linkedin.com/in/jane-example"


def test_edge_second_link_for_the_same_person_is_kept_as_a_note() -> None:
    parsed = parse("Jane Example\nhttps://linkedin.com/in/a\nhttps://linkedin.com/in/b")

    assert parsed.contacts[0].linkedin_url == "https://linkedin.com/in/a"
    assert parsed.contacts[0].note == "https://linkedin.com/in/b"


def test_edge_more_than_20_people_is_shortened() -> None:
    cell = "\n".join(f"Person{chr(65 + i)} Example - Engineer" for i in range(25))

    parsed = parse(cell)

    assert len(parsed.contacts) == 20
    assert parsed.shortened is True
    assert parsed.contacts[0].name == "PersonA Example"
    assert parsed.contacts[19].name == "PersonT Example"


def test_edge_exactly_20_people_is_not_shortened() -> None:
    cell = "\n".join(f"Person{chr(65 + i)} Example" for i in range(20))

    parsed = parse(cell)

    assert len(parsed.contacts) == 20
    assert parsed.shortened is False


def test_edge_labelled_email_and_phone_lines() -> None:
    cell = (
        "Lee Example - Recruiter\n"
        "email: lee@example.com\n"
        "Phone: +91 98765 43210\n"
        "Mia Demo\n"
        "tel: 0 80 1234 5678\n"
        "E-mail: mia@example.com"
    )

    parsed = parse(cell)

    assert [(c.name, c.email, c.phone) for c in parsed.contacts] == [
        ("Lee Example", "lee@example.com", "+91 98765 43210"),
        ("Mia Demo", "mia@example.com", "0 80 1234 5678"),
    ]


def test_edge_labelled_line_without_a_person_is_leftover() -> None:
    parsed = parse("email: hr@example.com")

    assert parsed.contacts == ()
    assert parsed.leftover == ("email: hr@example.com",)


def test_edge_labelled_note_lines_attach_to_the_person() -> None:
    parsed = parse("Jane Example\nnote: met at a meetup\nnote: asked to follow up in May")

    assert parsed.contacts[0].note == "met at a meetup\nasked to follow up in May"


def test_R3_short_capitalised_line_without_punctuation_is_a_new_person() -> None:
    parsed = parse("Jane Example\nJohn Sample")

    assert [c.name for c in parsed.contacts] == ["Jane Example", "John Sample"]


@pytest.mark.parametrize(
    "line",
    [
        "she said: call back later",
        "Waiting for a reply from them on this one",
        "Not sure if this is the right person.",
        "reply expected soon",
    ],
)
def test_R3_other_lines_after_a_person_are_note_lines(line: str) -> None:
    parsed = parse(f"Jane Example - Recruiter\n{line}")

    assert len(parsed.contacts) == 1
    assert parsed.contacts[0].note == line


def test_R3_empty_and_blank_cells_have_nothing() -> None:
    for cell in ("", "   \n \n"):
        parsed = parse(cell)
        assert parsed.contacts == ()
        assert parsed.leftover == ()


# --- FR-024: render, and the round trip -------------------------------------------------------

NAMES = ("Jane Example", "John Q Sample")
ROLES = (None, "Recruiter", "Engineering Manager")
TAGS = (None, "high", "medium", "low")
LINKS = (None, "https://www.linkedin.com/in/jane-example")
CONTACT_POINTS = (
    (None, None),
    ("jane@example.com", None),
    (None, "+91 98765 43210"),
    ("jane@example.com", "+91 98765 43210"),
)
NOTES = (None, "Prefers a short message, replies fast.", "First line.\nSecond line, after a call.")


def _cases() -> list[ParsedContact]:
    combos = list(itertools.product(NAMES, ROLES, TAGS, LINKS, CONTACT_POINTS, NOTES))
    # a spread of 30 cases that touches every value of every field, not the full product
    chosen = combos[:: len(combos) // 30][:30]
    return [
        ParsedContact(name, role, tag, link, email, phone, note)
        for name, role, tag, link, (email, phone), note in chosen
    ]


def test_FR024_render_gives_the_documented_shape() -> None:
    contact = ParsedContact(
        "Jane Example",
        "Recruiter",
        "high",
        "https://www.linkedin.com/in/jane-example",
        "jane@example.com",
        "+91 98765 43210",
        "Replies fast.",
    )

    assert render([contact]) == (
        "Jane Example - Recruiter [High]\n"
        "https://www.linkedin.com/in/jane-example\n"
        "email: jane@example.com\n"
        "phone: +91 98765 43210\n"
        "note: Replies fast."
    )


def test_FR024_render_then_parse_round_trips() -> None:
    cases = _cases()
    assert len(cases) == 30

    for contact in cases:
        parsed = parse(render([contact]))
        assert parsed.contacts == (contact,), render([contact])
        assert parsed.leftover == ()


def test_FR024_several_people_round_trip_together() -> None:
    people = _cases()[:5]
    # distinct names so none merges into another
    people = [
        ParsedContact(
            f"Person{chr(65 + i)} Example",
            c.role,
            c.confidence,
            c.linkedin_url,
            c.email,
            c.phone,
            c.note,
        )
        for i, c in enumerate(people)
    ]

    assert parse(render(people)).contacts == tuple(people)


def test_FR024_render_nothing_is_empty() -> None:
    assert render([]) == ""
