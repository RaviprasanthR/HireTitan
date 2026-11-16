"""Where a vendor's public job API keeps a posting's text, and how to read it (research R4).

``plan`` turns a posting's own link into the one request that returns its description, or none
when the link is not a posting of a known vendor (then the posting's own page is read instead).
The board and posting ids come from the link itself. Pure: no requests are made here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

from hiretitan.search.infra.careers_page.parse import html_to_text

GREENHOUSE_HOSTS = frozenset({"boards.greenhouse.io", "job-boards.greenhouse.io"})


@dataclass(frozen=True, slots=True)
class VendorCall:
    vendor: str
    url: str  # the one GET to make
    extract: Callable[[Any], str | None]  # the plain text in the parsed JSON answer, if any


def _join(*parts: str | None) -> str | None:
    text = "\n\n".join(p.strip() for p in parts if isinstance(p, str) and p.strip())
    return text or None


def _greenhouse(data: Any) -> str | None:
    content = data.get("content") if isinstance(data, dict) else None
    return html_to_text(content)


def _lever(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    lists = [
        _join(item.get("text"), html_to_text(item.get("content")))
        for item in data.get("lists") or []
        if isinstance(item, dict)
    ]
    plain = data.get("descriptionPlain") or html_to_text(data.get("description"))
    return _join(plain, *lists, data.get("additionalPlain"))


def _ashby(posting_id: str) -> Callable[[Any], str | None]:
    def extract(data: Any) -> str | None:
        jobs = data.get("jobs") if isinstance(data, dict) else None
        for job in jobs or []:
            if isinstance(job, dict) and job.get("id") == posting_id:
                return _join(
                    job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml"))
                )
        return None

    return extract


def _workday(data: Any) -> str | None:
    info = data.get("jobPostingInfo") if isinstance(data, dict) else None
    return html_to_text(info.get("jobDescription")) if isinstance(info, dict) else None


def _recruitee(data: Any) -> str | None:
    offer = data.get("offer") if isinstance(data, dict) else None
    if not isinstance(offer, dict):
        return None
    return _join(html_to_text(offer.get("description")), html_to_text(offer.get("requirements")))


def _segment(value: str) -> str:
    return quote(value, safe="")


def plan(url: str) -> VendorCall | None:
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or not parts.hostname:
        return None
    host = parts.hostname.lower()
    seg = [s for s in parts.path.split("/") if s]
    if host in GREENHOUSE_HOSTS and len(seg) >= 3 and seg[1] == "jobs" and seg[2].isdigit():
        api = f"https://boards-api.greenhouse.io/v1/boards/{_segment(seg[0])}/jobs/{seg[2]}"
        return VendorCall("greenhouse", api, _greenhouse)
    if host == "jobs.lever.co" and len(seg) >= 2:
        api = f"https://api.lever.co/v0/postings/{_segment(seg[0])}/{_segment(seg[1])}"
        return VendorCall("lever", api, _lever)
    if host == "jobs.ashbyhq.com" and len(seg) >= 2:
        api = f"https://api.ashbyhq.com/posting-api/job-board/{_segment(seg[0])}"
        return VendorCall("ashby", api, _ashby(seg[1]))
    if host.endswith(".myworkdayjobs.com") and "job" in seg[1:]:
        at = seg.index("job", 1)
        site, rest = seg[at - 1], seg[at + 1 :]
        if rest:
            tenant = host.split(".")[0]
            path = "/".join(_segment(s) for s in rest)
            api = f"https://{host}/wday/cxs/{_segment(tenant)}/{_segment(site)}/job/{path}"
            return VendorCall("workday", api, _workday)
    if host.endswith(".recruitee.com") and len(seg) >= 2 and seg[0] == "o":
        api = f"https://{host}/api/offers/{_segment(seg[1])}"
        return VendorCall("recruitee", api, _recruitee)
    return None
