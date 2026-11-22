"""The shape of an alert email with every word masked (2026-11-22). Pure.

A fixed reader depends on a site's layout: which line after the job link holds the company, which
the place. To fix a reader against a real alert without seeing anyone's mail, the person runs
``python -m hiretitan.mail_shape`` and shares this skeleton: every letter becomes ``x``/``X`` and
every digit ``9``, so line order, lengths, punctuation and link shapes stay visible and no title,
company, place or name does. A link keeps its host only when it is a job site's own domain.
"""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlsplit

from hiretitan.mail.domain.alerts import AlertJob
from hiretitan.mail.domain.mime import Flat
from hiretitan.mail.domain.senders import SITE_DOMAINS

_SITE_HOSTS = tuple(d for domains in SITE_DOMAINS.values() for d in domains)


def mask(text: str) -> str:
    """Letters become ``x`` (``X`` when upper case), digits ``9``; everything else stays."""
    return "".join(
        ("X" if ch.isupper() else "x") if ch.isalpha() else "9" if ch.isdigit() else ch
        for ch in text
    )


def _site_host(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in _SITE_HOSTS)


def link_shape(href: str) -> str:
    """The link with its path masked and its query dropped; the host kept only for a job site."""
    parts = urlsplit(href)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return mask(href)
    host = parts.hostname.lower()
    shown = host if _site_host(host) else mask(host)
    query = " ?…" if parts.query else ""
    return f"{parts.scheme}://{shown}{mask(parts.path)}{query}"


def _line_of(value: str | None, flat: Flat) -> str:
    """Where a value the reader took sits: ``Lnn``; ``none`` when it took nothing; ``?`` when the
    value is on no line (taken from link text, or put together)."""
    if not value:
        return "none"
    texts = [line.text for line in flat.lines]
    for exact in (True, False):
        for index, text in enumerate(texts):
            if (text == value) if exact else (value in text):
                return f"L{index:02d}"
    return "?"


def _link_of(href: str, flat: Flat) -> str:
    for number, link in enumerate(flat.links, start=1):
        if link.href == href:
            return str(number)
    return "?"


def skeleton(flat: Flat, jobs: Sequence[AlertJob]) -> list[str]:
    """The masked email: its lines, its links, and where each job's values came from."""
    out = [f"{flat.source} part · {len(flat.lines)} lines · {len(flat.links)} links"]
    for index, line in enumerate(flat.lines):
        muted = "(muted) " if line.muted else ""
        out.append(f"L{index:02d} {muted}{mask(line.text)}")
    for number, link in enumerate(flat.links, start=1):
        out.append(
            f"link {number} on L{link.line:02d} [{mask(link.text)}] -> {link_shape(link.href)}"
        )
    if flat.hidden:
        blocks = len(flat.hidden)
        out.append(f"hidden text: {blocks} block{'s' if blocks != 1 else ''}")
    if not jobs:
        out.append("the reader found no job")
    for number, job in enumerate(jobs, start=1):
        out.append(
            f"job {number}: title={_line_of(job.title, flat)}"
            f" company={_line_of(job.company, flat)}"
            f" location={_line_of(job.location, flat)}"
            f" link={_link_of(job.link, flat)}"
        )
    return out
