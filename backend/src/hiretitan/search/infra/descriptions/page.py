"""Read a posting's description from the posting's own page (feature 002i, research R4).

The page is fetched politely (robots.txt, spacing, cache, size limit) by the careers-page fetcher.
Its JSON-LD ``JobPosting`` description is used when there is one; otherwise the text a visitor
sees. A page built by scripts has neither, and is reported unreadable rather than guessed at.
"""

from __future__ import annotations

import re
from typing import Final

from hiretitan.search.application.ports import DescriptionResult, PageFetcherPort
from hiretitan.search.infra.careers_page.parse import parse_careers_page
from hiretitan.search.infra.careers_page.text import page_text

MIN_JSON_LD_CHARS: Final = 40
MIN_PAGE_CHARS: Final = 200
_LINK_NOTE: Final = re.compile(r"\s*<https?://[^<>\s]+>")  # page_text writes "text <link>"


async def read_page(pages: PageFetcherPort, url: str) -> DescriptionResult:
    fetched = await pages.fetch(url)
    if fetched.status != "ok" or not fetched.body:
        return DescriptionResult("unreadable", error=fetched.error or fetched.status)
    parsed = parse_careers_page(fetched.body, url)
    if parsed.via == "json_ld":
        best = max((p.description or "" for p in parsed.postings), key=len, default="")
        if len(best) >= MIN_JSON_LD_CHARS:
            return DescriptionResult("read", best)
    text = _LINK_NOTE.sub("", page_text(fetched.body, url)).strip()
    if len(text) < MIN_PAGE_CHARS:
        return DescriptionResult("unreadable", error="the page has no text to read")
    return DescriptionResult("read", text)
