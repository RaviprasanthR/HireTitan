"""The only requests the pinned career-ops providers may make (research R2, constitution VII).

Every enabled provider lists the hosts, HTTP methods and paths it uses. The contract test
``tests/contract/careerops/test_request_allowlist.py`` runs the real providers with every request
intercepted and fails on anything outside this list, so a career-ops upgrade that starts calling a
new endpoint or host cannot slip in unnoticed.

Each provider's paths were checked against the host's robots.txt (user agent ``HireTitan``):

* greenhouse: ``boards-api.greenhouse.io``, checked 2026-11-05, allows ``/v1/boards/...``.
* lever: ``api.lever.co``, checked 2026-11-05, allows ``/v0/postings/...``.
* ashby: ``api.ashbyhq.com``, checked 2026-11-05. The host answers 401 for robots.txt, which means
  no policy is published, so access is allowed (RFC 9309 section 2.3.1.3).
* workday: ``<tenant>.wdN.myworkdayjobs.com``, checked 2026-11-05, allows ``/wday/cxs/...``
  (POST for the search, GET for a posting).
* recruitee: ``<board>.recruitee.com``, checked 2026-11-05, allows ``/api/offers/``.
* zoho-recruit: ``<board>.zohorecruit.com``, checked 2026-11-05, allows ``/jobs/Careers``.
* amazon: ``www.amazon.jobs``, checked 2026-11-05, allows ``/en/search.json``.

Not listed, on purpose:

* **SmartRecruiters**: ``api.smartrecruiters.com/robots.txt`` says ``User-agent: *`` /
  ``Disallow: /`` and allows only LinkedInBot (checked 2026-11-05). Enable it only if that changes
  or SmartRecruiters confirms use of its public posting API in writing.
* **Keka**: its request path has not yet been checked against Keka's robots.txt (feasibility
  finding 1).

Workday is the only provider that sends a POST: its public job search is a POST to the board's own
``/jobs`` endpoint, and it only reads.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from re import fullmatch
from typing import Final
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class AllowedRequest:
    host: str  # fnmatch pattern on the host name
    method: str
    path: str  # regular expression that must match the whole path


_SEGMENT = r"[^/]+"

ALLOWED_REQUESTS: Final[dict[str, tuple[AllowedRequest, ...]]] = {
    "greenhouse": (
        AllowedRequest("boards-api.greenhouse.io", "GET", rf"/v1/boards/{_SEGMENT}/jobs"),
    ),
    "lever": (AllowedRequest("api.lever.co", "GET", rf"/v0/postings/{_SEGMENT}"),),
    "ashby": (AllowedRequest("api.ashbyhq.com", "GET", rf"/posting-api/job-board/{_SEGMENT}"),),
    "workday": (
        AllowedRequest("*.myworkdayjobs.com", "POST", rf"/wday/cxs/{_SEGMENT}/{_SEGMENT}/jobs"),
        AllowedRequest("*.myworkdayjobs.com", "GET", rf"/wday/cxs/{_SEGMENT}/{_SEGMENT}/job/.+"),
    ),
    "recruitee": (AllowedRequest("*.recruitee.com", "GET", r"/api/offers/"),),
    "zoho-recruit": (AllowedRequest("*.zohorecruit.com", "GET", r"/jobs/Careers(/[^/]+)?"),),
    "amazon": (AllowedRequest("www.amazon.jobs", "GET", r"/en/search\.json"),),
}


def is_allowed(provider: str, method: str, url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https":
        return False
    host = (parts.hostname or "").lower()
    return any(
        fnmatchcase(host, rule.host)
        and method.upper() == rule.method
        and fullmatch(rule.path, parts.path) is not None
        for rule in ALLOWED_REQUESTS.get(provider, ())
    )


def violations(provider: str, requests: Iterable[tuple[str, str]]) -> list[str]:
    """The ``METHOD url`` of every request the provider may not make."""
    return [f"{method} {url}" for method, url in requests if not is_allowed(provider, method, url)]
