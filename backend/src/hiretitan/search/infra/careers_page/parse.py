"""Read job postings out of a careers page (T052, research R3). Pure: it gets text, not a request.

Two ways, in order:

1. ``schema.org/JobPosting`` data (JSON-LD) in the page. Complete and reliable when present.
2. Links that look like jobs: a job-shaped path (``/careers/senior-python-developer``) or link
   text that names a role. Only the title and the link are known this way.

A page with neither is ``empty`` when it is real text with no openings, and ``unreadable`` when it
is an empty shell that needs JavaScript. Nothing here is trusted yet: the caller cleans and screens
every field like any other posting (constitution III).

Uses the standard library only (``html.parser`` and ``json``): no extra dependency to license.
"""

from __future__ import annotations

import contextlib
import html
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Final, Literal
from urllib.parse import urljoin, urlsplit

from hiretitan.search.application.ports import Posting
from hiretitan.search.domain.normalize import canonical_url

MAX_POSTINGS: Final = 300
TITLE_MAX: Final = 200
MIN_TEXT_CHARS: Final = 200  # less visible text than this is a shell that needs JavaScript

_JOB_PATH: Final = re.compile(
    r"/(?:jobs?|careers?|positions?|openings?|vacanc(?:y|ies)|opportunit(?:y|ies)|roles?"
    r"|postings?|requisitions?)/[^/?#]+",
    re.I,
)
_ROLE_WORD: Final = re.compile(
    r"\b(?:engineer|developer|designer|analyst|manager|architect|scientist|consultant"
    r"|administrator|specialist|lead|intern|officer|executive|associate|director|tester"
    r"|devops|sre|programmer|recruiter|writer|accountant)\b",
    re.I,
)
_NOT_JOBS: Final = frozenset(
    {
        "home", "about", "about us", "careers", "career", "jobs", "job", "apply", "apply now",
        "view all jobs", "all jobs", "see all jobs", "search jobs", "open positions", "openings",
        "contact", "contact us", "privacy", "privacy policy", "terms", "login", "sign in",
        "benefits", "culture", "teams", "our team", "locations", "blog", "back", "back to top",
        "learn more", "read more", "view all", "see all",
    }
)  # fmt: skip
_BLOCKS: Final = frozenset(
    {"p", "br", "li", "ul", "ol", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section"}
)
_HIDDEN: Final = frozenset({"script", "style", "noscript", "template"})


@dataclass(frozen=True, slots=True)
class ParseResult:
    status: Literal["found", "empty", "unreadable"]
    postings: list[Posting] = field(default_factory=list)
    via: Literal["json_ld", "links"] | None = None


# ---- one pass over the page ------------------------------------------------------------------


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld: list[str] = []
        self.links: list[tuple[str, str]] = []  # (href, text)
        self.text_chars = 0
        self._script: list[str] | None = None
        self._hidden = 0
        self._link: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script":
            kind = (values.get("type") or "").split(";")[0].strip().lower()
            self._script = [] if kind == "application/ld+json" else None
        if tag in _HIDDEN:
            self._hidden += 1
        elif tag == "a" and values.get("href"):
            self._link = (values["href"] or "", [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._flush_script()
        if tag in _HIDDEN and self._hidden:
            self._hidden -= 1
        elif tag == "a" and self._link:
            href, parts = self._link
            self.links.append((href, " ".join("".join(parts).split())))
            self._link = None

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script.append(data)
        elif not self._hidden:
            self.text_chars += len(data.strip())
            if self._link:
                self._link[1].append(data)

    def _flush_script(self) -> None:
        if self._script is not None:
            self.json_ld.append("".join(self._script))
            self._script = None

    def finish(self) -> None:
        try:
            self.close()
        finally:
            self._flush_script()


def _read(text: str) -> _Page:
    page = _Page()
    # a page the parser cannot read gives whatever it had read so far
    with contextlib.suppress(Exception):
        page.feed(text)
    with contextlib.suppress(Exception):
        page.finish()
    return page


# ---- JSON-LD ---------------------------------------------------------------------------------


def _nodes(value: Any) -> list[dict[str, Any]]:
    """Every object in the JSON-LD, looking inside lists and ``@graph``."""
    if isinstance(value, list):
        return [n for item in value for n in _nodes(item)]
    if not isinstance(value, dict):
        return []
    found = [value]
    for key in ("@graph", "itemListElement", "item"):
        found += _nodes(value.get(key))
    return found


def _is_job(node: dict[str, Any]) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return "JobPosting" in kinds


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        return " ".join(value.split()) or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _place(address: Any) -> str | None:
    if isinstance(address, str):
        return _text(address)
    if not isinstance(address, dict):
        return None
    parts = [_text(address.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry")]
    return ", ".join(p for p in parts if p) or None


def _location(node: dict[str, Any]) -> str | None:
    raw = node.get("jobLocation")
    places = raw if isinstance(raw, list) else [raw]
    named = [
        p for place in places if isinstance(place, dict) and (p := _place(place.get("address")))
    ]
    if named:
        return "; ".join(named)
    return "Remote" if node.get("jobLocationType") == "TELECOMMUTE" else None


def _date(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=UTC)


class _Plain(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCKS:
            self.out.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCKS:
            self.out.append("\n")

    def handle_data(self, data: str) -> None:
        self.out.append(data)


def _plain(markup: Any) -> str | None:
    if not isinstance(markup, str) or not markup.strip():
        return None
    if "&lt;" in markup:  # some sites escape the markup inside the JSON string
        markup = html.unescape(markup)
    parser = _Plain()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:
        return " ".join(markup.split()) or None
    lines = (" ".join(line.split()) for line in "".join(parser.out).split("\n"))
    return "\n".join(line for line in lines if line) or None


def _identifier(value: Any) -> str | None:
    if isinstance(value, dict):
        return _text(value.get("value"))
    return _text(value)


def _json_ld_postings(blocks: list[str], page_url: str) -> list[Posting]:
    postings: list[Posting] = []
    for block in blocks:
        try:
            data = json.loads(block)
        except ValueError:
            continue  # broken data on one script does not hide the others
        for node in _nodes(data):
            if not _is_job(node):
                continue
            title = _text(node.get("title")) or _text(node.get("name"))
            if not title:
                continue
            link = _text(node.get("url")) or _text(node.get("sameAs")) or page_url
            postings.append(
                Posting(
                    title=title[:TITLE_MAX],
                    url=urljoin(page_url, link),
                    location=_location(node),
                    posted_at=_date(node.get("datePosted")),
                    description=_plain(node.get("description")),
                    requisition_id=_identifier(node.get("identifier")),
                )
            )
    return postings


# ---- job-shaped links ------------------------------------------------------------------------


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _same_site(link_host: str, page_host: str) -> bool:
    return bool(link_host) and (
        link_host == page_host
        or link_host.endswith("." + page_host)
        or ("." in link_host and page_host.endswith("." + link_host))
    )


def _link_postings(links: list[tuple[str, str]], page_url: str) -> list[Posting]:
    page_host = _host(page_url)
    postings: list[Posting] = []
    for href, text in links:
        target = urljoin(page_url, href.strip())
        parts = urlsplit(target)
        title = text.strip()
        if parts.scheme not in ("http", "https") or not title or len(title) > TITLE_MAX:
            continue
        if title.lower().strip(" .!:") in _NOT_JOBS or not _same_site(_host(target), page_host):
            continue
        if len(title.split()) > 12:
            continue
        shaped = bool(_JOB_PATH.search(parts.path))
        named = bool(_ROLE_WORD.search(title)) and len(title.split()) <= 8
        if not (shaped or named):
            continue
        url = canonical_url(target)
        if url:
            postings.append(Posting(title=title, url=url))
    return postings


# ---- the entry point -------------------------------------------------------------------------


def _unique(postings: list[Posting]) -> list[Posting]:
    seen: set[tuple[str, str]] = set()
    unique: list[Posting] = []
    for posting in postings:
        key = (posting.url, posting.title.lower())
        if key not in seen:
            seen.add(key)
            unique.append(posting)
    return unique[:MAX_POSTINGS]


def parse_careers_page(text: str, page_url: str) -> ParseResult:
    page = _read(text)
    structured = _unique(_json_ld_postings(page.json_ld, page_url))
    if structured:
        return ParseResult("found", structured, "json_ld")
    links = _unique(_link_postings(page.links, page_url))
    if links:
        return ParseResult("found", links, "links")
    return ParseResult("empty" if page.text_chars >= MIN_TEXT_CHARS else "unreadable")
