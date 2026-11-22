"""The six fixed alert readers over the synthetic fixtures (T022): US2 AS3, FR-013, FR-017.

One module for all six sites (the same three tests per site): each reader must return every job in
every fixture email of its site, exactly as ``expected.yaml`` lists them, and nothing for a layout
it does not know. The layouts are guesses until the maintainer checks them (T005).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from hiretitan.mail.domain.alerts import JOBS_PER_EMAIL_MAX
from hiretitan.mail.domain.mime import flatten_message
from hiretitan.mail.domain.readers import READERS, read_alert

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mail"
SITES = ("linkedin", "naukri", "indeed", "foundit", "instahyre", "cutshort")
EMAILS: dict[str, dict[str, Any]] = yaml.safe_load((FIXTURES / "expected.yaml").read_text("utf-8"))[
    "emails"
]


def load(name: str) -> tuple[bytes, datetime]:
    return (FIXTURES / "eml" / name).read_bytes(), datetime.fromisoformat(EMAILS[name]["received"])


def of_site(site: str) -> list[str]:
    return sorted(n for n, e in EMAILS.items() if e["site"] == site and e.get("jobs"))


def as_tuples(jobs: Any) -> list[tuple[str, str | None, str | None, str, str | None]]:
    return [(j.title, j.company, j.location, j.link, j.posting_id) for j in jobs]


def expected_tuples(name: str) -> list[tuple[str, str | None, str | None, str, str | None]]:
    return [
        (j["title"], j["company"], j["location"], j["link"], j["posting_id"])
        for j in EMAILS[name]["jobs"]
    ]


def test_US2_AS3_every_site_has_a_reader_and_ten_fixture_emails() -> None:
    assert set(READERS) == set(SITES)
    for site in SITES:
        assert len([n for n in of_site(site) if n.startswith(site)]) == 10


@pytest.mark.parametrize("site", SITES)
def test_US2_AS3_every_job_in_the_email(site: str) -> None:
    for name in of_site(site):
        raw, received = load(name)

        jobs = read_alert(site, flatten_message(raw), received)

        assert as_tuples(jobs) == expected_tuples(name), name
        assert all(j.site == site and j.alert_date == received for j in jobs), name


@pytest.mark.parametrize("site", SITES)
def test_FR013_nothing_invented(site: str) -> None:
    saw_a_gap = False
    for name in of_site(site):
        raw, received = load(name)
        flat = flatten_message(raw)
        email_text = " ".join(line.text for line in flat.lines)
        for job in read_alert(site, flat, received):
            assert job.title in email_text, name
            if job.company is None or job.location is None:
                saw_a_gap = True
            if job.company is not None:
                assert job.company in email_text, name
            if job.location is not None:
                assert job.location in email_text, name
    if site in ("instahyre", "cutshort"):
        assert saw_a_gap  # the fixtures leave some company or place out; it stays empty


@pytest.mark.parametrize("site", SITES)
def test_edge_unknown_layout_returns_nothing(site: str) -> None:
    for name in ("unknown-01.eml", "unknown-02.eml", "unknown-03.eml"):
        raw, received = load(name)

        assert read_alert(site, flatten_message(raw), received) == [], name


@pytest.mark.parametrize("site", SITES)
def test_edge_another_sites_email_gives_nothing(site: str) -> None:
    other = "naukri" if site != "naukri" else "linkedin"
    raw, received = load(of_site(other)[0])

    assert read_alert(site, flatten_message(raw), received) == []


def test_FR014_instructions_in_the_email_are_never_a_job() -> None:
    for name in ("injection-01.eml", "injection-02.eml"):
        raw, received = load(name)

        jobs = read_alert("linkedin", flatten_message(raw), received)

        assert as_tuples(jobs) == expected_tuples(name), name
        assert not any("ignore" in (j.title + (j.company or "")).lower() for j in jobs)


def test_edge_a_text_only_alert_is_left_to_the_ai_fallback() -> None:
    raw, received = load("linkedin-01.eml")
    flat = flatten_message(raw)
    text_only = type(flat)("text", flat.lines, flat.links, flat.hidden)

    assert read_alert("linkedin", text_only, received) == []


def test_edge_a_site_with_no_reader_gives_nothing() -> None:
    raw, received = load("linkedin-01.eml")

    assert read_alert("other", flatten_message(raw), received) == []


def test_R13_at_most_60_jobs_from_one_email() -> None:
    cards = "".join(
        f"<p><a href='https://www.linkedin.com/jobs/view/{3900000000 + n}/'>Role {n}</a>"
        f"<br>Company {n}<br>Pune</p>"
        for n in range(80)
    )
    from email.message import EmailMessage

    message = EmailMessage()
    message["From"] = "jobalerts-noreply@linkedin.com"
    message.set_content(f"<html><body>{cards}</body></html>", subtype="html")

    jobs = read_alert(
        "linkedin",
        flatten_message(message.as_bytes()),
        datetime.fromisoformat("2026-11-16T10:00:00+05:30"),
    )

    assert len(jobs) == JOBS_PER_EMAIL_MAX


def test_FR013_the_same_posting_twice_in_one_email_is_one_job() -> None:
    from email.message import EmailMessage

    link = "https://www.linkedin.com/jobs/view/3900000001/"
    html = (
        f"<p><a href='{link}'>Data Engineer</a><br>Aspen Robotics<br>Pune</p>"
        f"<p><a href='{link}?trk=again'>Data Engineer</a><br>Aspen Robotics<br>Pune</p>"
    )
    message = EmailMessage()
    message["From"] = "jobalerts-noreply@linkedin.com"
    message.set_content(f"<html><body>{html}</body></html>", subtype="html")

    jobs = read_alert(
        "linkedin",
        flatten_message(message.as_bytes()),
        datetime.fromisoformat("2026-11-16T10:00:00+05:30"),
    )

    assert [j.posting_id for j in jobs] == ["3900000001"]
