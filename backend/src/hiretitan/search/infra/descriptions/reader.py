"""The description reader (feature 002i, FR-029): the vendor's public job API when the link is a
posting of a known vendor, else (or when that fails) the posting's own page.

Politeness: one request at a time per host, at least ``API_GAP_SECONDS`` apart (Lever asks for one
second); only requests the allowlist names; an honest user agent; a size cap; a timeout. A
description that cannot be read is an ``unreadable`` result, never an error.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Final
from urllib.parse import urlsplit

import httpx

from hiretitan.search.application.ports import DescribeRequest, DescriptionResult, PageFetcherPort
from hiretitan.search.infra.careers_page.fetcher import user_agent
from hiretitan.search.infra.descriptions.allowlist import is_allowed
from hiretitan.search.infra.descriptions.page import read_page
from hiretitan.search.infra.descriptions.vendors import VendorCall, plan

log = logging.getLogger(__name__)

API_GAP_SECONDS: Final = 1.0
API_TIMEOUT_SECONDS: Final = 20.0
MAX_BODY_BYTES: Final = 8 * 1024 * 1024  # an Ashby board lists every posting in one answer
BOARD_TTL_SECONDS: Final = 600.0  # one Ashby board answer serves a whole search
CACHE_MAX: Final = 64  # answers kept at once; a long-lived worker must not grow without bound


class DescriptionReader:
    def __init__(
        self,
        pages: PageFetcherPort,
        *,
        client: httpx.AsyncClient | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._pages = pages
        self._client = client
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_request: dict[str, float] = {}
        self._answers: dict[str, tuple[float, Any]] = {}

    async def read(self, job: DescribeRequest) -> DescriptionResult:
        call = plan(job.url)
        if call is not None:
            text = await self._from_vendor(call)
            if text:
                return DescriptionResult("read", text)
        try:
            return await read_page(self._pages, job.url)
        except Exception:
            log.exception("Could not read a posting's page")
            return DescriptionResult("unreadable", error="the page could not be read")

    # ---- the vendor's public API ----------------------------------------------------------

    async def _from_vendor(self, call: VendorCall) -> str | None:
        if not is_allowed(call.vendor, "GET", call.url):
            return None
        try:
            data = await self._get_json(call.url)
            text = call.extract(data)
        except Exception:  # a vendor answering oddly must never fail the search
            log.warning("The %s job API did not give a description", call.vendor, exc_info=True)
            return None
        return text.strip() if text and text.strip() else None

    async def _get_json(self, url: str) -> Any:
        cached = self._answers.get(url)
        if cached is not None and self._monotonic() - cached[0] < BOARD_TTL_SECONDS:
            return cached[1]
        host = urlsplit(url).netloc
        wait = self._last_request.get(host, -API_GAP_SECONDS) + API_GAP_SECONDS - self._monotonic()
        if wait > 0:
            await self._sleep(wait)
        self._last_request[host] = self._monotonic()
        client = self._client or httpx.AsyncClient()
        try:
            async with client.stream(
                "GET",
                url,
                headers={"User-Agent": user_agent(), "Accept": "application/json"},
                timeout=httpx.Timeout(API_TIMEOUT_SECONDS),
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise ValueError(f"the job API answered {response.status_code}")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BODY_BYTES:  # stop reading: the cap is on what is held
                        raise ValueError("the job API answer is too large")
        finally:
            if self._client is None:
                await client.aclose()
        data = json.loads(body)
        self._remember(url, data)
        return data

    def _remember(self, url: str, data: Any) -> None:
        """Keep an answer for a while: expired ones go first, then the oldest, up to the cap."""
        now = self._monotonic()
        for key in [k for k, (at, _) in self._answers.items() if now - at >= BOARD_TTL_SECONDS]:
            del self._answers[key]
        self._answers[url] = (now, data)
        while len(self._answers) > CACHE_MAX:
            del self._answers[next(iter(self._answers))]
