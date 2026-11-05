"""Job-board addresses: build one from a vendor and board id, or recognise one from a URL.

Board ids come from the shipped list, the person's CSV or their own edits, so they are checked
against a strict pattern before they are put into a URL: no slashes (except Workday's site), no
query strings, no dots outside Workday's tenant. The pinned providers also refuse hosts that are
not their own, which is the second wall.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit

from hiretitan.search.application.ports import BoardRef, DiscoveryResult

_SIMPLE_ID: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}")
_WORKDAY_ID: Final = re.compile(
    r"([a-z0-9][a-z0-9-]{0,60})\.(wd\d{1,2})/([A-Za-z0-9][A-Za-z0-9_-]{0,99})"
)
_AMAZON_QUERY: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,99}")

WORKDAY_MAX_PAGES: Final = 5  # 100 postings; a huge tenant must not take minutes


class BoardAddressError(ValueError):
    """The vendor or board id cannot be turned into a safe board address."""


@dataclass(frozen=True, slots=True)
class BoardRequest:
    company_id: str
    provider: str
    careers_url: str
    max_pages: int | None = None
    amazon: dict[str, str] | None = None

    def as_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "company_id": self.company_id,
            "provider": self.provider,
            "careers_url": self.careers_url,
        }
        if self.max_pages is not None:
            data["max_pages"] = self.max_pages
        if self.amazon is not None:
            data["amazon"] = self.amazon
        return data


def provider_id(vendor: str) -> str:
    """HireTitan names vendors with underscores, career-ops with hyphens."""
    return vendor.replace("_", "-")


def board_request(ref: BoardRef) -> BoardRequest:
    vendor, board_id = ref.vendor, ref.board_id
    company_id = str(ref.company_id)
    provider = provider_id(vendor)

    def simple(url_for: str) -> BoardRequest:
        if not _SIMPLE_ID.fullmatch(board_id):
            raise BoardAddressError(f"The board id {board_id!r} is not valid for {vendor}.")
        return BoardRequest(company_id, provider, url_for.format(board_id))

    match vendor:
        case "greenhouse":
            return simple("https://job-boards.greenhouse.io/{}")
        case "lever":
            return simple("https://jobs.lever.co/{}")
        case "ashby":
            return simple("https://jobs.ashbyhq.com/{}")
        case "smartrecruiters":
            return simple("https://jobs.smartrecruiters.com/{}")
        case "recruitee":
            return simple("https://{}.recruitee.com")
        case "zoho_recruit":
            return simple("https://{}.zohorecruit.com/jobs/Careers")
        case "workday":
            found = _WORKDAY_ID.fullmatch(board_id)
            if not found:
                raise BoardAddressError("A Workday board id looks like tenant.wd5/SiteName.")
            tenant, pod, site = found.groups()
            return BoardRequest(
                company_id,
                provider,
                f"https://{tenant}.{pod}.myworkdayjobs.com/{site}",
                max_pages=WORKDAY_MAX_PAGES,
            )
        case "amazon":
            if not _AMAZON_QUERY.fullmatch(board_id):
                raise BoardAddressError("An Amazon board id is a plain search phrase.")
            return BoardRequest(
                company_id,
                provider,
                "https://www.amazon.jobs/en/search",
                max_pages=WORKDAY_MAX_PAGES,
                amazon={"base_query": board_id},
            )
        case _:
            raise BoardAddressError(f"Provider {vendor} is not enabled.")


_WORKDAY_HOST: Final = re.compile(r"([a-z0-9][a-z0-9-]*)\.(wd\d{1,2})\.myworkdayjobs\.com")
_LOCALE: Final = re.compile(r"[a-z]{2}-[A-Z]{2}")


def discover_board(careers_url: str) -> DiscoveryResult | None:
    """Recognise a job-board address. This only reads the URL; it makes no request."""
    try:
        parts = urlsplit(careers_url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]
    first = segments[0] if segments else ""

    def hit(vendor: str, board_id: str) -> DiscoveryResult | None:
        return DiscoveryResult(vendor, board_id) if _SIMPLE_ID.fullmatch(board_id) else None

    if parts.scheme != "https":
        return None
    if host in {"job-boards.greenhouse.io", "boards.greenhouse.io"}:
        return hit("greenhouse", first)
    if host == "jobs.lever.co":
        return hit("lever", first)
    if host == "jobs.ashbyhq.com":
        return hit("ashby", first)
    if host == "jobs.smartrecruiters.com":
        return hit("smartrecruiters", first)
    if host.endswith(".recruitee.com") and host.count(".") == 2:
        return hit("recruitee", host.split(".")[0])
    if host.endswith(".zohorecruit.com") and host.count(".") == 2:
        return hit("zoho_recruit", host.split(".")[0])
    workday = _WORKDAY_HOST.fullmatch(host)
    if workday:
        site_segments = segments[1:] if segments and _LOCALE.fullmatch(first) else segments
        site = site_segments[0] if site_segments else ""
        candidate = f"{workday.group(1)}.{workday.group(2)}/{site}"
        if _WORKDAY_ID.fullmatch(candidate):
            return DiscoveryResult("workday", candidate)
    return None
