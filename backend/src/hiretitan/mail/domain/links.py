"""Posting ids and clean links, per job site (feature 002c, FR-022, research R4 and R6). Pure.

A link is read, never followed (FR-015). Each site has one rule that knows its job-link shape
(from general knowledge of the sites; the maintainer checks them against real alerts, T005). A link
no rule recognises has no posting id, is not a job link, and is kept exactly as the email gave it:
that includes click-tracking redirects, whose target cannot be known without following them.

``clean_link`` is the address used to recognise the same posting again: tracking parameters and
the site's mail-only path prefixes are dropped, so one posting has one clean link whichever alert
mentioned it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qs, urlsplit

LINK_MAX: Final = 2000


@dataclass(frozen=True, slots=True)
class _Rule:
    hosts: tuple[str, ...]  # the host or any subdomain of one of these
    posting_id: Callable[[str, str], str | None]  # (path, query) -> id
    clean: Callable[[str, str, str, str], str]  # (host, path, query, id) -> clean address


def _host_is(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


# ---- LinkedIn: /jobs/view/<digits>, also under /comm/ in alert emails ---------------------------
_LINKEDIN = re.compile(r"^/(?:comm/)?jobs/view/(?:[^/?]*-)?(\d{6,})/?$")

# ---- Naukri: /job-listings-<words>-<digits> -----------------------------------------------------
_NAUKRI = re.compile(r"^/job-listings-.+-(\d{6,})$")

# ---- Indeed: the job key ``jk`` is 16 hex characters, on several paths ---------------------------
_INDEED_PATH = re.compile(r"^/(?:rc/clk(?:/dl)?|viewjob|pagead/clk(?:/dl)?|m/viewjob)/?$")
_INDEED_KEY = re.compile(r"^[0-9a-f]{16}$")

# ---- foundit: /job/<words>-<digits> --------------------------------------------------------------
_FOUNDIT = re.compile(r"^/job/.+-(\d{5,})/?$")

# ---- Instahyre: /job-<digits>-<words> ------------------------------------------------------------
_INSTAHYRE = re.compile(r"^/job-(\d+)-[^/]+/?$")

# ---- Cutshort: /job/<words>/<id> -----------------------------------------------------------------
_CUTSHORT = re.compile(r"^/job/[^/]+/([A-Za-z0-9]{6,12})/?$")


def _by_path(pattern: re.Pattern[str]) -> Callable[[str, str], str | None]:
    def find(path: str, _query: str) -> str | None:
        match = pattern.match(path)
        return match.group(1) if match else None

    return find


def _indeed_id(path: str, query: str) -> str | None:
    if not _INDEED_PATH.match(path):
        return None
    key = (parse_qs(query).get("jk") or [""])[0]
    return key if _INDEED_KEY.match(key) else None


def _plain(host: str, path: str, _query: str, _id: str) -> str:
    return f"https://{host}{path}"


RULES: Final[dict[str, _Rule]] = {
    "linkedin": _Rule(
        ("linkedin.com",),
        _by_path(_LINKEDIN),
        lambda _h, _p, _q, pid: f"https://www.linkedin.com/jobs/view/{pid}/",
    ),
    "naukri": _Rule(("naukri.com",), _by_path(_NAUKRI), _plain),
    "indeed": _Rule(
        ("indeed.com",),
        _indeed_id,
        lambda host, _p, _q, pid: f"https://{host}/viewjob?jk={pid}",
    ),
    "foundit": _Rule(("foundit.in",), _by_path(_FOUNDIT), _plain),
    "instahyre": _Rule(("instahyre.com",), _by_path(_INSTAHYRE), _plain),
    "cutshort": _Rule(("cutshort.io",), _by_path(_CUTSHORT), _plain),
}


def _parts(site: str, link: str) -> tuple[_Rule, str, str, str] | None:
    rule = RULES.get(site)
    if rule is None or not link or len(link) > LINK_MAX:
        return None
    try:
        split = urlsplit(link.strip())
    except ValueError:
        return None
    host = (split.hostname or "").lower()
    if split.scheme not in ("http", "https") or not _host_is(host, rule.hosts):
        return None
    return rule, host, split.path, split.query


def on_site(site: str, link: str) -> bool:
    """For a built-in site: the link is on the site's own domain (or a subdomain), so an alert
    dressed as that site cannot add a job pointing elsewhere. An added sender's links (no rule)
    may be anywhere on the web."""
    rule = RULES.get(site)
    if rule is None:
        return True
    try:
        host = (urlsplit(link.strip()).hostname or "").lower()
    except ValueError:
        return False
    return _host_is(host, rule.hosts)


def posting_id(site: str, link: str) -> str | None:
    """The site's own number for the posting, when the link shows one."""
    parts = _parts(site, link)
    if parts is None:
        return None
    rule, _host, path, query = parts
    return rule.posting_id(path, query)


def is_job_link(site: str, link: str) -> bool:
    """A link to one posting on that site (and not a search, a profile or a redirect)."""
    return posting_id(site, link) is not None


def clean_link(site: str, link: str) -> str:
    """The posting's address without tracking; a link no rule knows comes back unchanged."""
    parts = _parts(site, link)
    if parts is None:
        return link
    rule, host, path, query = parts
    pid = rule.posting_id(path, query)
    if pid is None:
        return link
    return rule.clean(host, path, query, pid)
