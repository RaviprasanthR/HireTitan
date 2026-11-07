"""A scripted ``PageFetcherPort`` for tests: no network, no robots.txt, no waiting."""

from __future__ import annotations

from hiretitan.search.application.ports import PageFetch


class FakePages:
    """Answers each address with what the test scripted for it, and records every request."""

    def __init__(self) -> None:
        self._pages: dict[str, PageFetch] = {}
        self.fetched: list[str] = []

    def script(self, url: str, fetch: PageFetch) -> None:
        self._pages[url] = fetch

    def html(self, url: str, html: str) -> None:
        self.script(url, PageFetch("ok", html, url))

    async def fetch(self, url: str) -> PageFetch:
        self.fetched.append(url)
        return self._pages.get(url, PageFetch("failed", error="No page was scripted."))
