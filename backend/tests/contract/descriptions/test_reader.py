"""002i T014: reading a posting's own text from its source (FR-029, constitution VII).

Every response here is a small synthetic one, shaped like the vendor's public job API as
documented; nothing touches the network. Each vendor has one recorded answer, and the reader's
own requests are checked against the allowlist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from hiretitan.search.application.ports import DescribeRequest
from hiretitan.search.infra.careers_page.fetcher import CareersPageFetcher
from hiretitan.search.infra.descriptions.allowlist import is_allowed
from hiretitan.search.infra.descriptions.reader import API_GAP_SECONDS, DescriptionReader
from hiretitan.search.infra.descriptions.vendors import plan

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "descriptions"
ROBOTS_OPEN = "User-agent: *\nDisallow: /admin\n"
HTML = {"content-type": "text/html; charset=utf-8"}

GREENHOUSE = "https://boards.greenhouse.io/examplecorp/jobs/4001"
LEVER = "https://jobs.lever.co/examplecorp/11111111-2222-3333-4444-555555555555"
ASHBY = "https://jobs.ashbyhq.com/examplecorp/bbbb-2222"
WORKDAY = (
    "https://examplecorp.wd5.myworkdayjobs.com/en-US/ExampleSite/job/IN-Pune/Example-Role_JR1000"
)
RECRUITEE = "https://examplecorp.recruitee.com/o/backend-engineer"
OWN_PAGE = "https://careers.example.com/jobs/backend-engineer"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text("utf-8"))


async def public_dns(host: str) -> list[str]:
    return ["93.184.216.34"]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def reader(tmp_path: Path, clock: Clock) -> DescriptionReader:
    pages = CareersPageFetcher(
        tmp_path / "cache", monotonic=clock.monotonic, sleep=clock.sleep, resolve=public_dns
    )
    return DescriptionReader(pages, monotonic=clock.monotonic, sleep=clock.sleep)


# --- ids come from the posting's own link --------------------------------------------------


def test_FR029_ids_parsed_from_url() -> None:
    assert (
        plan(GREENHOUSE).url == "https://boards-api.greenhouse.io/v1/boards/examplecorp/jobs/4001"
    )  # type: ignore[union-attr]
    assert plan("https://job-boards.greenhouse.io/examplecorp/jobs/4001").vendor == "greenhouse"  # type: ignore[union-attr]
    assert plan(LEVER).url == (  # type: ignore[union-attr]
        "https://api.lever.co/v0/postings/examplecorp/11111111-2222-3333-4444-555555555555"
    )
    assert plan(ASHBY).url == "https://api.ashbyhq.com/posting-api/job-board/examplecorp"  # type: ignore[union-attr]
    assert plan(WORKDAY).url == (  # type: ignore[union-attr]
        "https://examplecorp.wd5.myworkdayjobs.com/wday/cxs/examplecorp/ExampleSite"
        "/job/IN-Pune/Example-Role_JR1000"
    )
    assert plan(RECRUITEE).url == "https://examplecorp.recruitee.com/api/offers/backend-engineer"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "url",
    [
        OWN_PAGE,  # a company's own page: no vendor
        "https://boards.greenhouse.io/examplecorp",  # a board, not a posting
        "https://jobs.lever.co/examplecorp",
        "https://examplecorp.wd5.myworkdayjobs.com/en-US/ExampleSite",
        "http://boards.greenhouse.io/examplecorp/jobs/4001",  # not https
        "https://evil.example.com/boards.greenhouse.io/x/jobs/1",  # the host decides, not the path
        "not a link",
    ],
)
def test_FR029_a_link_that_is_not_a_vendor_posting_has_no_vendor_call(url: str) -> None:
    assert plan(url) is None


# --- each vendor's recorded answer ---------------------------------------------------------


async def test_FR029_greenhouse_description(reader: DescriptionReader) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://boards-api.greenhouse.io/v1/boards/examplecorp/jobs/4001").respond(
            200, json=fixture("greenhouse.json")
        )
        result = await reader.read(DescribeRequest(GREENHOUSE))

    assert result.status == "read"
    assert result.text is not None
    assert "Build Python services." in result.text
    assert "4+ years of experience" in result.text
    assert "<p>" not in result.text  # plain text, not markup


async def test_FR029_lever_description(reader: DescriptionReader) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(
            "https://api.lever.co/v0/postings/examplecorp/11111111-2222-3333-4444-555555555555"
        ).respond(200, json=fixture("lever.json"))
        result = await reader.read(DescribeRequest(LEVER))

    assert result.status == "read"
    assert result.text is not None
    assert "Build Python services." in result.text
    assert "PostgreSQL" in result.text  # the lists (requirements) are part of the text
    assert "equal opportunity employer" in result.text


async def test_FR029_ashby_description(reader: DescriptionReader) -> None:
    with respx.mock(assert_all_called=True) as mock:
        board = mock.get("https://api.ashbyhq.com/posting-api/job-board/examplecorp").respond(
            200, json=fixture("ashby.json")
        )
        result = await reader.read(DescribeRequest(ASHBY))
        again = await reader.read(DescribeRequest("https://jobs.ashbyhq.com/examplecorp/aaaa-1111"))

    assert (result.status, result.text) == ("read", "Build Python services.")  # the right posting
    assert again.text == "Other job."
    assert board.call_count == 1  # one board call serves every posting of that board


async def test_FR029_workday_description(reader: DescriptionReader) -> None:
    api = (
        "https://examplecorp.wd5.myworkdayjobs.com/wday/cxs/examplecorp/ExampleSite"
        "/job/IN-Pune/Example-Role_JR1000"
    )
    with respx.mock(assert_all_called=True) as mock:
        mock.get(api).respond(200, json=fixture("workday.json"))
        result = await reader.read(DescribeRequest(WORKDAY))

    assert result.status == "read"
    assert result.text is not None
    assert "Build Python services." in result.text
    assert "Hybrid in Chennai." in result.text


async def test_FR029_recruitee_description(reader: DescriptionReader) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://examplecorp.recruitee.com/api/offers/backend-engineer").respond(
            200, json=fixture("recruitee.json")
        )
        result = await reader.read(DescribeRequest(RECRUITEE))

    assert result.status == "read"
    assert result.text is not None
    assert "Build Python services." in result.text
    assert "PostgreSQL" in result.text


# --- the posting's own page ----------------------------------------------------------------

JSON_LD_PAGE = (
    "<html><head><script type='application/ld+json'>"
    '{"@type": "JobPosting", "title": "Backend Engineer", '
    '"description": "<p>Build Python services for payments.</p><p>4+ years of experience.</p>"}'
    "</script></head><body><h1>Backend Engineer</h1></body></html>"
)
PLAIN_PAGE = (
    "<html><body><nav>Home Careers</nav><main><h1>Backend Engineer</h1>"
    "<p>" + "We build payment services in Python and PostgreSQL. " * 12 + "</p>"
    "</main></body></html>"
)
JS_ONLY_PAGE = "<html><body><div id='root'></div><script>window.app()</script></body></html>"


async def test_FR029_page_json_ld_description(reader: DescriptionReader) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://careers.example.com/robots.txt").respond(200, text=ROBOTS_OPEN)
        mock.get(OWN_PAGE).respond(200, text=JSON_LD_PAGE, headers=HTML)
        result = await reader.read(DescribeRequest(OWN_PAGE))

    assert result.status == "read"
    assert result.text is not None
    assert "Build Python services for payments." in result.text


async def test_FR029_page_main_text_fallback(reader: DescriptionReader) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://careers.example.com/robots.txt").respond(200, text=ROBOTS_OPEN)
        mock.get(OWN_PAGE).respond(200, text=PLAIN_PAGE, headers=HTML)
        result = await reader.read(DescribeRequest(OWN_PAGE))

    assert result.status == "read"
    assert result.text is not None
    assert "payment services in Python and PostgreSQL" in result.text


async def test_FR029_a_page_with_no_text_is_unreadable(reader: DescriptionReader) -> None:
    """A page built by scripts has nothing to read without a browser (no JSON-LD, no text)."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://careers.example.com/robots.txt").respond(200, text=ROBOTS_OPEN)
        mock.get(OWN_PAGE).respond(200, text=JS_ONLY_PAGE, headers=HTML)
        result = await reader.read(DescribeRequest(OWN_PAGE))

    assert result.status == "unreadable"


async def test_FR029_vendor_mismatch_falls_back_to_page(reader: DescriptionReader) -> None:
    """The vendor's API answers something unexpected: the posting's own page is read instead."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://boards-api.greenhouse.io/v1/boards/examplecorp/jobs/4001").respond(
            404, json={"error": "not found"}
        )
        mock.get("https://boards.greenhouse.io/robots.txt").respond(200, text=ROBOTS_OPEN)
        mock.get(GREENHOUSE).respond(200, text=PLAIN_PAGE, headers=HTML)
        result = await reader.read(DescribeRequest(GREENHOUSE))

    assert result.status == "read"
    assert result.text is not None
    assert "payment services in Python and PostgreSQL" in result.text


async def test_FR029_an_unexpected_json_shape_falls_back_to_page(
    reader: DescriptionReader,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://boards-api.greenhouse.io/v1/boards/examplecorp/jobs/4001").respond(
            200, json={"unexpected": True}
        )
        mock.get("https://boards.greenhouse.io/robots.txt").respond(200, text=ROBOTS_OPEN)
        mock.get(GREENHOUSE).respond(200, text=PLAIN_PAGE, headers=HTML)
        result = await reader.read(DescribeRequest(GREENHOUSE))

    assert result.status == "read"


async def test_FR029_robots_disallow_gives_unreadable(reader: DescriptionReader) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://careers.example.com/robots.txt").respond(
            200, text="User-agent: *\nDisallow: /\n"
        )
        page = mock.get(OWN_PAGE).respond(200, text=PLAIN_PAGE, headers=HTML)
        result = await reader.read(DescribeRequest(OWN_PAGE))

    assert result.status == "unreadable"
    assert not page.called  # the page was never requested


async def test_FR029_a_network_error_is_unreadable_not_an_exception(
    reader: DescriptionReader,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://boards-api.greenhouse.io/v1/boards/examplecorp/jobs/4001").mock(
            side_effect=httpx.ConnectError("no route")
        )
        mock.get("https://boards.greenhouse.io/robots.txt").mock(
            side_effect=httpx.ConnectError("no route")
        )
        result = await reader.read(DescribeRequest(GREENHOUSE))

    assert result.status == "unreadable"


# --- politeness ----------------------------------------------------------------------------


async def test_FR029_vendor_calls_to_one_host_are_spaced(
    reader: DescriptionReader, clock: Clock
) -> None:
    other = "https://boards.greenhouse.io/examplecorp/jobs/4002"
    with respx.mock(assert_all_called=False) as mock:
        mock.get(
            url__regex=r"https://boards-api\.greenhouse\.io/v1/boards/examplecorp/jobs/\d+"
        ).respond(200, json=fixture("greenhouse.json"))
        await reader.read(DescribeRequest(GREENHOUSE))
        await reader.read(DescribeRequest(other))

    assert clock.slept == [API_GAP_SECONDS]  # the second call to the same host waited


async def test_FR029_description_requests_stay_on_allowlist(
    reader: DescriptionReader,
) -> None:
    """Every request the reader makes for every vendor is one the allowlist names, or a page
    request on the posting's own host (which robots.txt and the page fetcher govern)."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r"https://boards-api\.greenhouse\.io/.*").respond(
            200, json=fixture("greenhouse.json")
        )
        mock.get(url__regex=r"https://api\.lever\.co/.*").respond(200, json=fixture("lever.json"))
        mock.get(url__regex=r"https://api\.ashbyhq\.com/.*").respond(
            200, json=fixture("ashby.json")
        )
        mock.get(url__regex=r"https://.*\.myworkdayjobs\.com/.*").respond(
            200, json=fixture("workday.json")
        )
        mock.get(url__regex=r"https://.*\.recruitee\.com/.*").respond(
            200, json=fixture("recruitee.json")
        )
        for link in (GREENHOUSE, LEVER, ASHBY, WORKDAY, RECRUITEE):
            await reader.read(DescribeRequest(link))
        seen = [(call.request.method, str(call.request.url)) for call in mock.calls]

    assert len(seen) == 5
    for method, url in seen:
        assert any(
            is_allowed(vendor, method, url)
            for vendor in ("greenhouse", "lever", "ashby", "workday", "recruitee")
        ), f"{method} {url}"


def test_FR029_the_allowlist_refuses_other_hosts_methods_and_paths() -> None:
    api = "https://boards-api.greenhouse.io/v1/boards/examplecorp/jobs/4001"
    assert is_allowed("greenhouse", "GET", api)
    assert not is_allowed("greenhouse", "POST", api)
    assert not is_allowed("greenhouse", "GET", api.replace("https", "http"))
    assert not is_allowed("greenhouse", "GET", "https://evil.example.com/v1/boards/a/jobs/1")
    assert not is_allowed("greenhouse", "GET", "https://boards-api.greenhouse.io/v1/boards/a")
    assert not is_allowed("smartrecruiters", "GET", "https://api.smartrecruiters.com/v1/x")


# --- limits found by the story review -----------------------------------------------------------


@pytest.mark.parametrize(
    "link",
    [
        "https://examplecorp.wd5.myworkdayjobs.com/en-US/ExampleSite/job/../../secret",
        "https://examplecorp.wd5.myworkdayjobs.com/en-US/ExampleSite/job/./x",
        "https://boards.greenhouse.io/../jobs/4001",
        "https://jobs.lever.co/examplecorp/..",
    ],
)
def test_FR029_a_link_with_dot_segments_has_no_vendor_call(link: str) -> None:
    assert plan(link) is None


async def test_FR029_the_answer_cache_stays_small(reader: DescriptionReader, clock: Clock) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r"https://boards-api\.greenhouse\.io/.*").respond(
            200, json=fixture("greenhouse.json")
        )
        for number in range(200):
            await reader.read(
                DescribeRequest(f"https://boards.greenhouse.io/examplecorp/jobs/{4000 + number}")
            )

    assert len(reader._answers) <= 64


async def test_FR029_old_answers_are_dropped_when_new_ones_arrive(
    reader: DescriptionReader, clock: Clock
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r"https://boards-api\.greenhouse\.io/.*").respond(
            200, json=fixture("greenhouse.json")
        )
        await reader.read(DescribeRequest(GREENHOUSE))
        clock.now += 3600  # an hour later
        await reader.read(DescribeRequest("https://boards.greenhouse.io/examplecorp/jobs/4002"))

    assert len(reader._answers) == 1


async def test_FR029_a_body_over_the_size_limit_is_not_kept(
    reader: DescriptionReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hiretitan.search.infra.descriptions.reader.MAX_BODY_BYTES", 200)
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://boards-api.greenhouse.io/v1/boards/examplecorp/jobs/4001").respond(
            200, json={"content": "x" * 5000}
        )
        mock.get("https://boards.greenhouse.io/robots.txt").respond(404)
        mock.get(GREENHOUSE).respond(404)
        result = await reader.read(DescribeRequest(GREENHOUSE))

    assert result.status == "unreadable"
