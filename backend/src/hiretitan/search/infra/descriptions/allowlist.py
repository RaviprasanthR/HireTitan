"""The only requests the description reader may make to a job board's public API (research R4).

Each request reads one posting (or, for Ashby, one board's posting list) from the same public API
HireTitan already uses to list jobs. A posting's own page is not here: it is read through the
careers-page fetcher, which honours the site's robots.txt.

robots.txt of each API host, checked 2026-11-16 (user agent ``HireTitan``):

* greenhouse: ``boards-api.greenhouse.io`` disallows only ``/embed/``, so ``/v1/boards/...`` is
  allowed.
* lever: ``api.lever.co`` allows ``/`` with ``Crawl-delay: 1``; the reader spaces its requests to
  one host by at least one second (``API_GAP_SECONDS``).
* ashby: ``api.ashbyhq.com`` answers 401 for robots.txt, which means no policy is published, so
  access is allowed (RFC 9309 section 2.3.1.3).
* workday: ``<tenant>.wdN.myworkdayjobs.com`` allows ``/wday/cxs/...``; the same endpoint the job
  search already uses to read a posting (see ``infra/careerops/allowlist.py``).
* recruitee: ``<board>.recruitee.com`` allows ``/api/offers/`` (checked 2026-11-05 for the listing;
  the single-offer path is under the same prefix).

The contract test ``tests/contract/descriptions/test_reader.py`` runs the reader with every request
intercepted and fails on anything outside this list.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from re import fullmatch
from typing import Final
from urllib.parse import urlsplit

from hiretitan.search.infra.careerops.allowlist import AllowedRequest

_SEGMENT = r"[^/]+"

ALLOWED_REQUESTS: Final[dict[str, tuple[AllowedRequest, ...]]] = {
    "greenhouse": (
        AllowedRequest("boards-api.greenhouse.io", "GET", rf"/v1/boards/{_SEGMENT}/jobs/\d+"),
    ),
    "lever": (AllowedRequest("api.lever.co", "GET", rf"/v0/postings/{_SEGMENT}/{_SEGMENT}"),),
    "ashby": (AllowedRequest("api.ashbyhq.com", "GET", rf"/posting-api/job-board/{_SEGMENT}"),),
    "workday": (
        AllowedRequest("*.myworkdayjobs.com", "GET", rf"/wday/cxs/{_SEGMENT}/{_SEGMENT}/job/.+"),
    ),
    "recruitee": (AllowedRequest("*.recruitee.com", "GET", rf"/api/offers/{_SEGMENT}"),),
}


def is_allowed(vendor: str, method: str, url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https":
        return False
    host = (parts.hostname or "").lower()
    return any(
        fnmatchcase(host, rule.host)
        and method.upper() == rule.method
        and fullmatch(rule.path, parts.path) is not None
        for rule in ALLOWED_REQUESTS.get(vendor, ())
    )
