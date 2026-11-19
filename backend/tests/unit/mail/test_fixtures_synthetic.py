"""The alert fixtures stay synthetic and complete (T002): constitution VIII, SC-002's test set."""

from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from pathlib import Path

import yaml

from hiretitan.mail.infra.seed import load_seed

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mail"
SEED = Path(__file__).resolve().parents[3] / "seed" / "mail_senders.yaml"
SITES = ("linkedin", "naukri", "indeed", "foundit", "instahyre", "cutshort")
ADDRESS = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")


def _expected() -> dict[str, dict]:  # type: ignore[type-arg]
    return yaml.safe_load((FIXTURES / "expected.yaml").read_text("utf-8"))["emails"]  # type: ignore[no-any-return]


def test_SC002_at_least_ten_emails_per_builtin_site() -> None:
    expected = _expected()
    for site in SITES:
        assert sum(1 for e in expected.values() if e["site"] == site) >= 10, site
    assert sum(1 for e in expected.values() if e["site"] == "other") >= 3
    assert sum(1 for name in expected if name.startswith("injection-")) >= 2


def test_SC002_every_email_file_is_listed_and_the_other_way_round() -> None:
    files = {p.name for p in (FIXTURES / "eml").glob("*.eml")}
    assert files == set(_expected())


def test_FR_no_real_address_anywhere() -> None:
    site_addresses = {s.address for s in load_seed(SEED)}
    for path in (FIXTURES / "eml").glob("*.eml"):
        text = path.read_text("utf-8")
        for address in ADDRESS.findall(text):
            host = address.split("@", 1)[1].lower()
            synthetic = host == "example.invalid" or host.endswith(".example.invalid")
            assert address.lower() in site_addresses or synthetic, (path.name, address)


def test_FR_every_listed_link_is_in_the_email() -> None:
    for name, entry in _expected().items():
        message = BytesParser(policy=policy.default).parsebytes(
            (FIXTURES / "eml" / name).read_bytes()
        )
        body = message.get_body(("html",))
        assert body is not None, name
        html = body.get_content()
        for job in entry["jobs"]:
            assert job["link"].replace("&", "&amp;") in html or job["link"] in html, (
                name,
                job["link"],
            )


def test_FR_expected_sender_matches_the_header() -> None:
    for name, entry in _expected().items():
        message = BytesParser(policy=policy.default).parsebytes(
            (FIXTURES / "eml" / name).read_bytes()
        )
        assert entry["sender"] in str(message["From"]), name


def test_FR_the_readme_says_synthetic() -> None:
    assert "made up" in (FIXTURES / "README.md").read_text("utf-8")
