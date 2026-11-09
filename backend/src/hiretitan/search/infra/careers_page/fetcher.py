"""Read a company's careers page politely (T051, FR-013, constitution VII).

* ``robots.txt`` is honoured (protego), cached per host for 24 hours. A page it disallows is never
  requested. A missing file (4xx) allows reading; one that cannot be reached (5xx, network) means
  "try again later" and nothing is read (RFC 9309).
* At least 2 seconds between requests to the same host, robots.txt included.
* ``ETag`` / ``Last-Modified`` are kept on disk, so an unchanged page costs one small request.
* ``GET`` only, a 15 second timeout, a 2 MB body cap, and an honest ``User-Agent``.
* Redirects are followed by hand (at most 3), and each target is checked and spaced like a page.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time as _time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

import httpx
from protego import Protego

from hiretitan import __version__
from hiretitan.search.application.ports import PageFetch

MIN_GAP_SECONDS: Final = 2.0
ROBOTS_TTL_SECONDS: Final = 24 * 60 * 60
TIMEOUT_SECONDS: Final = 15.0
MAX_BODY_BYTES: Final = 2 * 1024 * 1024
MAX_REDIRECTS: Final = 3
HTML_TYPES: Final = ("text/html", "application/xhtml+xml")
REPO_URL: Final = "https://github.com/RaviprasanthR/HireTitan"


def user_agent() -> str:
    return f"HireTitan/{__version__} (+{REPO_URL})"


class _TooLargeError(Exception):
    pass


class CareersPageFetcher:
    def __init__(
        self,
        cache_dir: Path,
        *,
        client: httpx.AsyncClient | None = None,
        monotonic: Callable[[], float] = _time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._cache_dir = cache_dir
        self._client = client
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_request: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # host -> (when it was read, rules); None rules means "allow everything"
        self._robots: dict[str, tuple[float, Protego | None]] = {}

    # ---- public ---------------------------------------------------------------------------

    async def fetch(self, url: str) -> PageFetch:
        current = url.strip()
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(current)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                return PageFetch("failed", error="Only http and https links can be read.")
            try:
                allowed = await self._allowed(parts.scheme, parts.netloc, current)
                if allowed is not None:
                    return allowed
                outcome = await self._get(current)
            except httpx.HTTPError as error:
                return PageFetch(
                    "failed", error=f"Could not reach the page: {type(error).__name__}"
                )
            if isinstance(outcome, PageFetch):
                return outcome
            current = outcome  # a redirect target: check and space it like any page
        return PageFetch("failed", error="The page redirects too many times.")

    # ---- robots.txt -----------------------------------------------------------------------

    async def _allowed(self, scheme: str, netloc: str, url: str) -> PageFetch | None:
        """None when the page may be read; otherwise the result to return."""
        rules = self._robots.get(netloc)
        if rules is None or self._monotonic() - rules[0] > ROBOTS_TTL_SECONDS:
            response = await self._request(netloc, f"{scheme}://{netloc}/robots.txt")
            if response.status_code >= 500:
                return PageFetch("failed", error="The site's robots.txt could not be read.")
            parsed = Protego.parse(response.text) if response.status_code < 400 else None
            rules = (self._monotonic(), parsed)
            self._robots[netloc] = rules
        if rules[1] is not None and not rules[1].can_fetch(url, user_agent()):
            return PageFetch(
                "blocked", error="The site does not allow automatic reading of this page."
            )
        return None

    # ---- requests -------------------------------------------------------------------------

    async def _spaced(self, host: str) -> None:
        wait = self._last_request.get(host, -MIN_GAP_SECONDS) + MIN_GAP_SECONDS - self._monotonic()
        if wait > 0:
            await self._sleep(wait)
        self._last_request[host] = self._monotonic()

    async def _request(
        self,
        host: str,
        url: str,
        headers: dict[str, str] | None = None,
        *,
        limit: int | None = None,
    ) -> httpx.Response:
        """One GET, spaced per host. With ``limit``, a longer body raises ``_TooLargeError``."""
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            await self._spaced(host)
            client = self._client or httpx.AsyncClient()
            try:
                async with client.stream(
                    "GET",
                    url,
                    headers={"User-Agent": user_agent(), **(headers or {})},
                    timeout=httpx.Timeout(TIMEOUT_SECONDS),
                    follow_redirects=False,
                ) as response:
                    announced = response.headers.get("content-length", "")
                    cap = MAX_BODY_BYTES if limit is None else limit
                    if announced.isdigit() and int(announced) > cap:
                        raise _TooLargeError
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > cap:
                            raise _TooLargeError
                    return httpx.Response(
                        response.status_code,
                        headers=response.headers,
                        content=bytes(body),
                        request=response.request,
                    )
            finally:
                if self._client is None:
                    await client.aclose()

    async def _get(self, url: str) -> PageFetch | str:
        """Read one page. Returns the result, or the address to follow."""
        cached = self._load(url)
        headers: dict[str, str] = {}
        if cached:
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]
        netloc = urlsplit(url).netloc
        try:
            response = await self._request(netloc, url, headers)
        except _TooLargeError:
            return PageFetch("unreadable", error="The page is too large to read.")
        code = response.status_code
        if code == 304 and cached:
            return PageFetch("ok", cached["body"], url, from_cache=True)
        if code in (301, 302, 303, 307, 308) and response.headers.get("location"):
            return urljoin(url, response.headers["location"])
        if code >= 400 or code == 304:
            return PageFetch("failed", error=f"The page answered with status {code}.")
        kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if kind not in HTML_TYPES:
            return PageFetch("unreadable", error="The page is not a web page we can read.")
        text = response.content.decode(response.charset_encoding or "utf-8", errors="replace")
        if not text.strip():
            return PageFetch("unreadable", error="The page is empty.")
        self._store(url, response.headers, text)
        return PageFetch("ok", text, url)

    # ---- the on-disk cache ----------------------------------------------------------------

    def _path(self, url: str) -> Path:
        return self._cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()}.json"

    def _load(self, url: str) -> dict[str, Any] | None:
        try:
            data = json.loads(self._path(url).read_text("utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) and isinstance(data.get("body"), str) else None

    def _store(self, url: str, headers: httpx.Headers, body: str) -> None:
        etag, modified = headers.get("etag"), headers.get("last-modified")
        if not (etag or modified):
            return  # nothing to ask "has it changed?" with
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            path = self._path(url)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"url": url, "etag": etag, "last_modified": modified, "body": body}),
                "utf-8",
            )
            temporary.replace(path)
        except OSError:
            pass  # a cache that cannot be written only costs a full request next time
