"""Posting ids and clean links per site (T021): FR-022, research R4 and R6.

Every job in the synthetic fixtures is checked: the id read from the link is the one the fixture
lists. Links are never followed; a link no rule knows is kept exactly as the email gave it.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from hiretitan.mail.domain.links import clean_link, is_job_link, posting_id

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mail"
SITES = ("linkedin", "naukri", "indeed", "foundit", "instahyre", "cutshort")
TRACKING = ("utm_", "trackingid", "refid", "midtoken", "src", "sid", "xp", "px", "from", "qd")


def fixture_jobs() -> list[tuple[str, str, str]]:
    emails = yaml.safe_load((FIXTURES / "expected.yaml").read_text("utf-8"))["emails"]
    found = []
    for email in emails.values():
        if email["site"] in SITES:
            found.extend((email["site"], job["link"], job["posting_id"]) for job in email["jobs"])
    return found


JOBS = fixture_jobs()


def test_FR022_the_fixtures_cover_every_site() -> None:
    assert {site for site, _link, _pid in JOBS} == set(SITES)
    assert len(JOBS) >= 60


@pytest.mark.parametrize(("site", "link", "expected"), JOBS)
def test_FR022_posting_id_from_link(site: str, link: str, expected: str) -> None:
    assert is_job_link(site, link)
    assert posting_id(site, link) == expected


@pytest.mark.parametrize(("site", "link", "expected"), JOBS)
def test_FR022_clean_link_drops_tracking(site: str, link: str, expected: str) -> None:
    clean = clean_link(site, link)

    query = {k.lower() for k in parse_qs(urlsplit(clean).query)}
    assert not {k for k in query if k.startswith(TRACKING)} - {"jk"}  # only Indeed's own id stays
    assert clean_link(site, clean) == clean  # cleaning twice changes nothing
    # the same posting reached through another tracking tail has the same clean link
    assert clean_link(site, link + ("&" if "?" in link else "?") + "utm_source=other") == clean
    assert expected in clean or site == "indeed"


def test_FR022_one_posting_one_clean_link_whatever_the_tracking() -> None:
    a = "https://www.linkedin.com/comm/jobs/view/3978721496/?trackingId=1&refId=x&midToken=m"
    b = "https://www.linkedin.com/jobs/view/3978721496?refId=other"

    assert clean_link("linkedin", a) == clean_link("linkedin", b)
    assert clean_link("linkedin", a) == "https://www.linkedin.com/jobs/view/3978721496/"


def test_FR022_indeed_keeps_only_the_job_key() -> None:
    link = "https://in.indeed.com/rc/clk/dl?jk=5fce192ee983f1ec&from=ja&qd=2418549&rd=x42"

    assert clean_link("indeed", link) == "https://in.indeed.com/viewjob?jk=5fce192ee983f1ec"
    assert posting_id("indeed", link) == "5fce192ee983f1ec"


@pytest.mark.parametrize(
    ("site", "link"),
    [
        # a click-tracking redirect: the posting cannot be told from the address
        ("linkedin", "https://click.linkedin.com/e/v2?url=https%3A%2F%2Fwww.linkedin.com%2Fjobs"),
        (
            "naukri",
            "https://www.google.com/url?q=https://www.naukri.com/job-listings-x-191100000001",
        ),
        ("indeed", "https://cts.indeed.com/v3/H4sIAAAA"),
        ("foundit", "https://email.foundit.in/ls/click?upn=u001.abc"),
        ("linkedin", "https://www.linkedin.com/jobs/search/?keywords=backend"),
        ("naukri", "https://www.naukri.com/mnjuser/homepage"),
        ("linkedin", "https://www.linkedin.com/comm/jobs/alerts?midToken=abc"),
    ],
)
def test_edge_redirect_link_kept_as_given_never_followed(site: str, link: str) -> None:
    assert not is_job_link(site, link)
    assert posting_id(site, link) is None
    assert clean_link(site, link) == link


def test_edge_a_link_on_the_wrong_site_is_not_that_sites_job() -> None:
    link = "https://www.linkedin.com/comm/jobs/view/3978721496/"

    assert not is_job_link("naukri", link)
    assert posting_id("naukri", link) is None


def test_edge_a_site_with_no_rule_keeps_the_link_as_given() -> None:
    link = "https://careers.example.invalid/roles/backend?utm_source=x"

    assert posting_id("other", link) is None
    assert clean_link("other", link) == link
    assert not is_job_link("other", link)


@pytest.mark.parametrize(
    "link",
    [
        "not a link",
        "",
        "ftp://www.linkedin.com/jobs/view/3978721496/",
        "https://www.linkedin.com.evil.example.invalid/jobs/view/3978721496/",
        "https://evil.example.invalid/?u=https://www.linkedin.com/jobs/view/3978721496/",
    ],
)
def test_edge_lookalike_and_malformed_links_are_not_job_links(link: str) -> None:
    assert not is_job_link("linkedin", link)
    assert posting_id("linkedin", link) is None
    assert clean_link("linkedin", link) == link
