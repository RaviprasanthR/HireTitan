"""T051: reading a careers page politely (FR-013, constitution VII).

Pages and robots.txt are recorded text; nothing here touches the network.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from hiretitan import __version__
from hiretitan.search.infra.careers_page.fetcher import (
    MAX_BODY_BYTES,
    MIN_GAP_SECONDS,
    ROBOTS_TTL_SECONDS,
    CareersPageFetcher,
    user_agent,
)

PAGE = "https://careers.example.com/jobs"
HTML = "<html><body><h1>Jobs</h1><a href='/jobs/1'>Backend Engineer</a></body></html>"
ROBOTS_OPEN = "User-agent: *\nDisallow: /admin\n"
ROBOTS_CLOSED = "User-agent: *\nDisallow: /\n"
HTML_HEADERS = {"content-type": "text/html; charset=utf-8"}


class FakeTime:
    """A clock the fetcher can wait on without really waiting."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def time() -> FakeTime:
    return FakeTime()


async def public_dns(host: str) -> list[str]:
    """Every test host is on a public address, so no test needs the network's DNS."""
    return ["93.184.216.34"]


@pytest.fixture
def fetcher(tmp_path: Path, time: FakeTime) -> CareersPageFetcher:
    return CareersPageFetcher(
        tmp_path / "cache", monotonic=time.monotonic, sleep=time.sleep, resolve=public_dns
    )


def robots(
    mock: respx.MockRouter, text: str = ROBOTS_OPEN, host: str = "careers.example.com"
) -> respx.Route:
    return mock.get(f"https://{host}/robots.txt").respond(200, text=text)


async def test_a_gzip_page_and_gzip_robots_are_read(fetcher: CareersPageFetcher) -> None:
    """Most real sites compress; the decoded body must not be decoded a second time."""
    import gzip

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://careers.example.com/robots.txt").respond(
            200,
            content=gzip.compress(ROBOTS_OPEN.encode()),
            headers={"content-encoding": "gzip", "content-type": "text/plain"},
        )
        mock.get(PAGE).respond(
            200,
            content=gzip.compress(HTML.encode()),
            headers={**HTML_HEADERS, "content-encoding": "gzip"},
        )

        result = await fetcher.fetch(PAGE)

    assert result.status == "ok"
    assert result.body == HTML


async def test_a_page_is_read_and_returned_as_text(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(200, text=HTML, headers=HTML_HEADERS)

        result = await fetcher.fetch(PAGE)

    assert result.status == "ok"
    assert result.body == HTML
    assert result.from_cache is False


async def test_FR013_robots_disallowed_page_not_fetched(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock, ROBOTS_CLOSED)
        page = mock.get(PAGE).respond(200, text=HTML, headers=HTML_HEADERS)

        result = await fetcher.fetch(PAGE)

    assert result.status == "blocked"
    assert result.body is None
    assert not page.called  # the page itself was never requested


async def test_only_the_disallowed_paths_are_blocked(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get("https://careers.example.com/admin/jobs").respond(
            200, text=HTML, headers=HTML_HEADERS
        )
        mock.get(PAGE).respond(200, text=HTML, headers=HTML_HEADERS)

        blocked = await fetcher.fetch("https://careers.example.com/admin/jobs")
        allowed = await fetcher.fetch(PAGE)

    assert (blocked.status, allowed.status) == ("blocked", "ok")


async def test_a_missing_robots_file_allows_reading(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://careers.example.com/robots.txt").respond(404)
        mock.get(PAGE).respond(200, text=HTML, headers=HTML_HEADERS)

        assert (await fetcher.fetch(PAGE)).status == "ok"


async def test_an_unreachable_robots_file_means_do_not_read(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://careers.example.com/robots.txt").respond(503)
        page = mock.get(PAGE).respond(200, text=HTML, headers=HTML_HEADERS)

        result = await fetcher.fetch(PAGE)

    assert result.status == "failed"
    assert not page.called


async def test_robots_is_cached_per_host_for_a_day(
    fetcher: CareersPageFetcher, time: FakeTime
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        route = robots(mock)
        mock.get(PAGE).respond(200, text=HTML, headers=HTML_HEADERS)
        mock.get("https://careers.example.com/other").respond(200, text=HTML, headers=HTML_HEADERS)

        await fetcher.fetch(PAGE)
        await fetcher.fetch("https://careers.example.com/other")
        assert route.call_count == 1

        time.now += ROBOTS_TTL_SECONDS + 1
        await fetcher.fetch(PAGE)
        assert route.call_count == 2


async def test_FR013_two_second_spacing_per_host(
    fetcher: CareersPageFetcher, time: FakeTime
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        robots(mock, host="other.example.org")
        mock.get(PAGE).respond(200, text=HTML, headers=HTML_HEADERS)
        mock.get("https://careers.example.com/two").respond(200, text=HTML, headers=HTML_HEADERS)
        mock.get("https://other.example.org/jobs").respond(200, text=HTML, headers=HTML_HEADERS)

        await fetcher.fetch(PAGE)  # robots.txt then the page: already two requests to the host
        first_wait = list(time.slept)
        await fetcher.fetch("https://careers.example.com/two")
        waits_same_host = list(time.slept)
        time.slept.clear()
        await fetcher.fetch("https://other.example.org/jobs")

    # the second request to a host waits until 2 s after the one before it
    assert first_wait
    assert all(w == pytest.approx(MIN_GAP_SECONDS) for w in first_wait)
    assert len(waits_same_host) == len(first_wait) + 1
    assert waits_same_host[-1] == pytest.approx(MIN_GAP_SECONDS)
    # another host has its own clock: its first request (robots.txt) does not wait
    assert time.slept == [pytest.approx(MIN_GAP_SECONDS)]  # only its page waits for its robots.txt


async def test_no_wait_when_enough_time_has_passed(
    fetcher: CareersPageFetcher, time: FakeTime
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(200, text=HTML, headers=HTML_HEADERS)
        await fetcher.fetch(PAGE)
        time.slept.clear()
        time.now += 60

        await fetcher.fetch(PAGE)

    assert time.slept == []


async def test_FR013_conditional_request_uses_cache(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        page = mock.get(PAGE).mock(
            side_effect=[
                httpx.Response(
                    200,
                    text=HTML,
                    headers=HTML_HEADERS
                    | {"etag": '"v1"', "last-modified": "Mon, 02 Nov 2026 10:00:00 GMT"},
                ),
                httpx.Response(304),
            ]
        )

        first = await fetcher.fetch(PAGE)
        second = await fetcher.fetch(PAGE)

    sent = page.calls[1].request.headers
    assert sent["if-none-match"] == '"v1"'
    assert sent["if-modified-since"] == "Mon, 02 Nov 2026 10:00:00 GMT"
    assert (first.from_cache, second.from_cache) == (False, True)
    assert second.status == "ok"
    assert second.body == HTML


async def test_the_cache_survives_a_new_fetcher(tmp_path: Path, time: FakeTime) -> None:
    def make() -> CareersPageFetcher:
        return CareersPageFetcher(
            tmp_path / "cache", monotonic=time.monotonic, sleep=time.sleep, resolve=public_dns
        )

    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        page = mock.get(PAGE).mock(
            side_effect=[
                httpx.Response(200, text=HTML, headers=HTML_HEADERS | {"etag": '"v1"'}),
                httpx.Response(304),
            ]
        )
        await make().fetch(PAGE)
        again = await make().fetch(PAGE)

    assert page.calls[1].request.headers["if-none-match"] == '"v1"'
    assert (again.status, again.body, again.from_cache) == ("ok", HTML, True)


async def test_a_changed_page_replaces_the_cached_one(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).mock(
            side_effect=[
                httpx.Response(200, text=HTML, headers=HTML_HEADERS | {"etag": '"v1"'}),
                httpx.Response(200, text="<p>new</p>", headers=HTML_HEADERS | {"etag": '"v2"'}),
                httpx.Response(304),
            ]
        )
        await fetcher.fetch(PAGE)
        changed = await fetcher.fetch(PAGE)
        unchanged = await fetcher.fetch(PAGE)

    assert (changed.body, changed.from_cache) == ("<p>new</p>", False)
    assert (unchanged.body, unchanged.from_cache) == ("<p>new</p>", True)


async def test_FR013_user_agent_is_honest(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots_route = robots(mock)
        page = mock.get(PAGE).respond(200, text=HTML, headers=HTML_HEADERS)

        await fetcher.fetch(PAGE)

    expected = f"HireTitan/{__version__} (+https://github.com/RaviprasanthR/HireTitan)"
    assert user_agent() == expected
    assert robots_route.calls[0].request.headers["user-agent"] == expected
    assert page.calls[0].request.headers["user-agent"] == expected
    assert page.calls[0].request.method == "GET"


async def test_body_over_2mb_is_unreadable(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(200, content=b"a" * (MAX_BODY_BYTES + 1), headers=HTML_HEADERS)

        result = await fetcher.fetch(PAGE)

    assert result.status == "unreadable"
    assert result.body is None


async def test_a_body_exactly_at_the_limit_is_read(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(200, content=b"a" * MAX_BODY_BYTES, headers=HTML_HEADERS)

        assert (await fetcher.fetch(PAGE)).status == "ok"


async def test_a_page_that_is_not_html_is_unreadable(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(
            200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"}
        )

        assert (await fetcher.fetch(PAGE)).status == "unreadable"


async def test_http_errors_and_timeouts_are_failures_not_exceptions(
    fetcher: CareersPageFetcher,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(500)
        mock.get("https://careers.example.com/slow").mock(side_effect=httpx.ReadTimeout("slow"))
        mock.get("https://careers.example.com/gone").respond(404)

        server = await fetcher.fetch(PAGE)
        slow = await fetcher.fetch("https://careers.example.com/slow")
        gone = await fetcher.fetch("https://careers.example.com/gone")

    assert [r.status for r in (server, slow, gone)] == ["failed", "failed", "failed"]
    assert all(r.error for r in (server, slow, gone))


async def test_a_redirect_to_another_host_is_checked_against_its_robots(
    fetcher: CareersPageFetcher,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        robots(mock, ROBOTS_CLOSED, host="boards.example.net")
        mock.get(PAGE).respond(302, headers={"location": "https://boards.example.net/acme"})
        target = mock.get("https://boards.example.net/acme").respond(
            200, text=HTML, headers=HTML_HEADERS
        )

        result = await fetcher.fetch(PAGE)

    assert result.status == "blocked"
    assert not target.called


async def test_a_redirect_to_an_allowed_page_is_followed(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(301, headers={"location": "/careers"})
        mock.get("https://careers.example.com/careers").respond(
            200, text=HTML, headers=HTML_HEADERS
        )

        result = await fetcher.fetch(PAGE)

    assert (result.status, result.final_url) == ("ok", "https://careers.example.com/careers")


async def test_a_redirect_loop_gives_up(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(302, headers={"location": PAGE})

        assert (await fetcher.fetch(PAGE)).status == "failed"


@pytest.mark.parametrize(
    "url", ["ftp://careers.example.com/jobs", "file:///etc/passwd", "careers", ""]
)
async def test_only_http_and_https_pages_are_read(fetcher: CareersPageFetcher, url: str) -> None:
    result = await fetcher.fetch(url)

    assert result.status == "failed"


# --- a link must never lead the app to a private address (SSRF, constitution VII) -------------

PRIVATE_LINKS = [
    "http://127.0.0.1:8000/admin",
    "http://localhost/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/jobs",
    "http://192.168.1.1/",
    "http://172.16.0.9/",
    "http://100.64.0.1/",
    "http://0.0.0.0/",
    "http://[::1]/",
    "http://[fd00::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[::127.0.0.1]/",
    "http://[64:ff9b::a9fe:a9fe]/",
    "http://[2002:7f00:1::]/",
]


def dns_of(table: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    async def resolve(host: str) -> list[str]:
        if host not in table:
            raise OSError("no such host")
        return table[host]

    return resolve


@pytest.mark.parametrize("link", PRIVATE_LINKS)
async def test_SSRF_a_private_address_is_never_requested(link: str, tmp_path: Path) -> None:
    fetcher = CareersPageFetcher(tmp_path / "cache", resolve=dns_of({"localhost": ["127.0.0.1"]}))
    with respx.mock(assert_all_called=False) as mock:
        result = await fetcher.fetch(link)
        requested = len(mock.calls)

    assert result.status == "blocked"
    assert result.body is None
    assert requested == 0  # not even robots.txt was asked for


async def test_SSRF_a_name_that_resolves_to_a_private_address_is_not_requested(
    tmp_path: Path,
) -> None:
    fetcher = CareersPageFetcher(
        tmp_path / "cache", resolve=dns_of({"intranet.example.com": ["10.1.2.3"]})
    )
    with respx.mock(assert_all_called=False) as mock:
        result = await fetcher.fetch("https://intranet.example.com/jobs")
        requested = len(mock.calls)

    assert result.status == "blocked"
    assert requested == 0


async def test_SSRF_one_private_record_among_public_ones_is_enough_to_refuse(
    tmp_path: Path,
) -> None:
    fetcher = CareersPageFetcher(
        tmp_path / "cache", resolve=dns_of({"mixed.example.com": ["93.184.216.34", "127.0.0.1"]})
    )
    with respx.mock(assert_all_called=False) as mock:
        result = await fetcher.fetch("https://mixed.example.com/jobs")
        requested = len(mock.calls)

    assert result.status == "blocked"
    assert requested == 0


async def test_SSRF_a_redirect_into_a_private_address_is_not_followed(
    tmp_path: Path, time: FakeTime
) -> None:
    fetcher = CareersPageFetcher(
        tmp_path / "cache",
        monotonic=time.monotonic,
        sleep=time.sleep,
        resolve=dns_of({"careers.example.com": ["93.184.216.34"]}),
    )
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(
            302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
        )
        result = await fetcher.fetch(PAGE)
        hosts = {call.request.url.host for call in mock.calls}

    assert result.status == "blocked"
    assert hosts == {"careers.example.com"}  # the private host was never contacted


async def test_SSRF_a_redirect_may_not_drop_from_https_to_http(
    fetcher: CareersPageFetcher,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(302, headers={"location": "http://careers.example.com/jobs"})
        plain = mock.get("http://careers.example.com/jobs").respond(
            200, text=HTML, headers=HTML_HEADERS
        )
        result = await fetcher.fetch(PAGE)

    assert result.status == "failed"
    assert not plain.called


async def test_SSRF_a_host_that_cannot_be_resolved_fails_without_a_request(tmp_path: Path) -> None:
    fetcher = CareersPageFetcher(tmp_path / "cache", resolve=dns_of({}))
    with respx.mock(assert_all_called=False) as mock:
        result = await fetcher.fetch("https://nowhere.example.com/jobs")
        requested = len(mock.calls)

    assert result.status == "failed"
    assert requested == 0


async def test_SSRF_a_public_address_is_read_as_before(fetcher: CareersPageFetcher) -> None:
    with respx.mock(assert_all_called=False) as mock:
        robots(mock)
        mock.get(PAGE).respond(200, text=HTML, headers=HTML_HEADERS)
        result = await fetcher.fetch(PAGE)

    assert result.status == "ok"


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("64:ff9b::a9fe:a9fe", False),  # NAT64 of 169.254.169.254
        ("64:ff9b::808:808", True),  # NAT64 of 8.8.8.8
        ("2002:7f00:1::", False),  # 6to4 of 127.0.0.1
        ("2002:808:808::", True),  # 6to4 of 8.8.8.8
        ("::127.0.0.1", False),  # IPv4-compatible
    ],
)
def test_SSRF_embedded_ipv4_is_judged_as_the_ipv4_it_hides(address: str, public: bool) -> None:
    from hiretitan.search.infra.careers_page.fetcher import is_public_address

    assert is_public_address(address) is public
