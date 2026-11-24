"""Alert senders (T003): FR-010. The shipped list is read once, fail-fast, and never trusted."""

from __future__ import annotations

from pathlib import Path

import pytest

from hiretitan.mail.domain.senders import SITES, SenderError, normalize_address, parse_seed
from hiretitan.mail.infra.seed import load_seed

SEED = Path(__file__).resolve().parents[3] / "seed" / "mail_senders.yaml"


def test_FR010_builtin_sites_present() -> None:
    senders = load_seed(SEED)

    sites = {s.site for s in senders}
    assert {"linkedin", "naukri", "indeed", "foundit", "instahyre", "cutshort"} <= sites
    assert all(s.site in SITES and s.site != "other" for s in senders)
    assert len({s.address for s in senders}) == len(senders)


def test_FR010_addresses_are_lower_case_and_valid() -> None:
    for sender in load_seed(SEED):
        assert sender.address == sender.address.lower()
        assert normalize_address(sender.address) == sender.address


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"senders": "linkedin"},
        {"senders": {"linkedin": "a@b.co"}},
        {"senders": {"linkedin": ["no-at-sign"]}},
        {"senders": {"linkedin": ["a@b@c.co"]}},
        {"senders": {"linkedin": ["a@b.co", "A@B.CO"]}},  # the same address twice
        {"senders": {"linkedin": ["x" * 320 + "@b.co"]}},
        {"senders": {"somesite": ["a@b.co"]}},
        {"senders": {"other": ["a@b.co"]}},  # "other" is for the person's own senders
    ],
)
def test_FR010_bad_seed_fails_fast(raw: object) -> None:
    with pytest.raises(SenderError):
        parse_seed(raw)


def test_FR010_a_valid_seed_is_normalised() -> None:
    senders = parse_seed({"senders": {"naukri": ["  Alerts@Naukri.com "]}})

    assert [(s.site, s.address) for s in senders] == [("naukri", "alerts@naukri.com")]


@pytest.mark.parametrize(
    "address",
    ["", "plain", "a@b", "a b@c.co", "@c.co", "a@", "a@@c.co", "a@c .co", "x" * 320 + "@c.co"],
)
def test_FR010_a_bad_address_is_refused(address: str) -> None:
    with pytest.raises(SenderError):
        normalize_address(address)


@pytest.mark.parametrize("address", ["-a@c.co", "+a@c.co", "-@c.co", "-from@c.co"])
def test_FR009_a_leading_minus_or_plus_is_refused(address: str) -> None:
    # "-x" negates a term in Gmail search, so an address starting with it would exclude mail
    with pytest.raises(SenderError):
        normalize_address(address)


def test_FR009_a_minus_or_plus_inside_the_address_is_fine() -> None:
    assert normalize_address("no-reply+jobs@c.co") == "no-reply+jobs@c.co"


def test_FR009_a_gmail_query_character_cannot_ride_along() -> None:
    # addresses go into a search query, so characters with a meaning there are refused
    for address in ('a"b@c.co', "a(b@c.co", "a)b@c.co", "a{b@c.co", "a:b@c.co"):
        with pytest.raises(SenderError):
            normalize_address(address)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Job Alerts <Alerts@Naukri.com>", "alerts@naukri.com"),
        ("alerts@naukri.com", "alerts@naukri.com"),
        # a display name that is itself an address is how a listed sender gets borrowed
        ('"jobalerts-noreply@linkedin.com" <x@evil.example.invalid>', ""),
        ("LinkedIn jobalerts-noreply@linkedin.com <x@evil.example.invalid>", ""),
        ("", ""),
        ("no address here", ""),
        ("Bad <a b@c.co>", ""),
        ("Nul <a" + chr(0) + "b@c.co>", ""),
        ("Long <" + "x" * 400 + "@c.co>", ""),
    ],
)
def test_SEC_the_sender_of_an_email_is_its_address_or_nothing(header: str, expected: str) -> None:
    from hiretitan.mail.domain.senders import address_from_header

    assert address_from_header(header) == expected
