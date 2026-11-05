"""T036: masking emails, phones and links before text reaches the AI (FR-008a, research R4)."""

from __future__ import annotations

import pytest

from hiretitan.platform.untrusted.mask_contacts import Contacts, mask_contacts, strip_placeholders

HEADER = (
    "Jane Example\n"
    "jane.example@example.com | +91 90000 00001 | linkedin.com/in/jane-example-fake\n"
    "Pune, India | https://github.com/jane-example-fake | https://jane.example.com/portfolio\n"
)


def test_FR008a_email_phone_link_masked() -> None:
    result = mask_contacts(HEADER, default_region="IN")

    assert "jane.example@example.com" not in result.text
    assert "90000" not in result.text
    assert "linkedin.com" not in result.text
    assert "github.com" not in result.text
    assert "[[EMAIL_1]]" in result.text
    assert "[[PHONE_1]]" in result.text
    assert result.text.count("[[LINK_") == 3
    assert result.contacts.emails == ("jane.example@example.com",)
    assert result.contacts.phones == ("+91 90000 00001",)
    assert result.contacts.links == (
        "linkedin.com/in/jane-example-fake",
        "https://github.com/jane-example-fake",
        "https://jane.example.com/portfolio",
    )


def test_FR008a_name_not_masked() -> None:
    result = mask_contacts(HEADER, default_region="IN")
    assert result.text.startswith("Jane Example\n")
    assert "Pune, India" in result.text


@pytest.mark.parametrize(
    ("text", "region", "expected"),
    [
        ("+1 (415) 555-2671", "IN", "+1 (415) 555-2671"),
        ("+44 20 7946 0958", "IN", "+44 20 7946 0958"),
        ("+91 90000 00001", "US", "+91 90000 00001"),
        ("(415) 555-2671", "US", "(415) 555-2671"),
        ("90000 00001", "IN", "90000 00001"),
        ("+49 30 901820", "IN", "+49 30 901820"),
    ],
)
def test_FR008a_international_phone_formats(text: str, region: str, expected: str) -> None:
    result = mask_contacts(f"Call me: {text} anytime", default_region=region)
    assert result.text == "Call me: [[PHONE_1]] anytime"
    assert result.contacts.phones == (expected,)


@pytest.mark.parametrize(
    "text",
    [
        "Acme Corp 2013 - 2017",
        "06/2017 - 12/2020",
        "Jan 2021 - Present",
        "Cut costs by 1,200,000 INR across 12 teams",
        "Served 2M requests per day",
        "Score 95.5 out of 100",
    ],
)
def test_dates_and_numbers_are_not_masked_as_phones(text: str) -> None:
    result = mask_contacts(text, default_region="IN")
    assert result.text == text
    assert result.contacts.phones == ()


def test_repeated_values_share_one_placeholder() -> None:
    text = "a@example.com and again a@example.com and b@example.com"
    result = mask_contacts(text, default_region="IN")
    assert result.text == "[[EMAIL_1]] and again [[EMAIL_1]] and [[EMAIL_2]]"
    assert result.contacts.emails == ("a@example.com", "b@example.com")


def test_email_domain_is_not_also_masked_as_a_link() -> None:
    result = mask_contacts("mail me at jane@github.com now", default_region="IN")
    assert result.text == "mail me at [[EMAIL_1]] now"
    assert result.contacts.links == ()


def test_digits_inside_urls_are_not_masked_as_phones() -> None:
    result = mask_contacts("see https://example.com/p/9000000001 here", default_region="IN")
    assert result.text == "see [[LINK_1]] here"
    assert result.contacts.phones == ()


def test_trailing_punctuation_stays_outside_the_link() -> None:
    result = mask_contacts("Portfolio: https://jane.example.com/work.", default_region="IN")
    assert result.text == "Portfolio: [[LINK_1]]."
    assert result.contacts.links == ("https://jane.example.com/work",)


def test_text_without_contacts_is_unchanged() -> None:
    text = "Built APIs in Python.\nLed a team of 5 engineers."
    result = mask_contacts(text, default_region="IN")
    assert result.text == text
    assert result.contacts == Contacts()


def test_strip_placeholders() -> None:
    assert (
        strip_placeholders("Reach [[EMAIL_1]] or [[PHONE_2]] via [[LINK_10]].") == "Reach or via."
    )
    assert strip_placeholders("no placeholders here") == "no placeholders here"
    assert strip_placeholders("[[EMAIL_1]]") == ""


@pytest.mark.parametrize("filler", ["a", "a.", "a-b"])
def test_long_text_without_an_at_sign_is_masked_quickly(filler: str) -> None:
    import time

    text = (filler * 30_000)[:30_000]
    started = time.perf_counter()
    result = mask_contacts(text, default_region="IN")
    elapsed = time.perf_counter() - started

    assert result.text == text
    assert elapsed < 0.2, f"took {elapsed:.2f}s"
