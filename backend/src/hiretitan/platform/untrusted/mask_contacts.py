"""Mask contact details before text reaches the AI (FR-008a, research R4).

Emails, phone numbers and links become ``[[EMAIL_n]]``, ``[[PHONE_n]]`` and ``[[LINK_n]]``.
The originals are returned separately and go straight to the review screen; they are never
sent. The AI output schema has no contact fields, and any placeholder it echoes is removed
with ``strip_placeholders``. The name is not masked (no reliable way to find it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from phonenumbers import Leniency, PhoneNumberMatcher

# The local part is bounded (RFC 5321: 64), so a long run of letters is not rescanned quadratically.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_LINK = re.compile(
    r"https?://[^\s<>\"')\]]+"
    r"|\b(?:www\.)?(?:linkedin\.com/in|github\.com|gitlab\.com)/[^\s<>\"')\]]+",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"[ \t]*\[\[(?:EMAIL|PHONE|LINK)_\d+\]\]")
_TRAILING = ".,;:!?"


@dataclass(frozen=True, slots=True)
class Contacts:
    emails: tuple[str, ...] = ()
    phones: tuple[str, ...] = ()
    links: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Masked:
    text: str
    contacts: Contacts


class _Numbering:
    """Gives each distinct value the next placeholder number; repeats reuse theirs."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.values: list[str] = []

    def placeholder(self, value: str) -> str:
        if value not in self.values:
            self.values.append(value)
        return f"[[{self.kind}_{self.values.index(value) + 1}]]"


def _replace_spans(text: str, spans: list[tuple[int, int, str]], numbering: _Numbering) -> str:
    out: list[str] = []
    last = 0
    for start, end, value in spans:
        out.append(text[last:start])
        out.append(numbering.placeholder(value))
        last = end
    out.append(text[last:])
    return "".join(out)


def _mask_emails(text: str, numbering: _Numbering) -> str:
    spans = [(m.start(), m.end(), m.group(0)) for m in _EMAIL.finditer(text)]
    return _replace_spans(text, spans, numbering)


def _mask_links(text: str, numbering: _Numbering) -> str:
    spans: list[tuple[int, int, str]] = []
    for m in _LINK.finditer(text):
        value = m.group(0).rstrip(_TRAILING)
        spans.append((m.start(), m.start() + len(value), value))
    return _replace_spans(text, spans, numbering)


def _phone_spans(text: str, region: str) -> list[tuple[int, int, str]]:
    found: dict[tuple[int, int], str] = {}
    for m in PhoneNumberMatcher(text, region, Leniency.VALID):
        found[(m.start, m.end)] = m.raw_string
    # International numbers that are only "possible": accepted when written with a + sign.
    for m in PhoneNumberMatcher(text, region, Leniency.POSSIBLE):
        overlaps = any(m.start < e and s < m.end for s, e in found)
        if m.raw_string.lstrip().startswith("+") and not overlaps:
            found[(m.start, m.end)] = m.raw_string
    return [(s, e, v) for (s, e), v in sorted(found.items())]


def _mask_phones(text: str, region: str, numbering: _Numbering) -> str:
    return _replace_spans(text, _phone_spans(text, region), numbering)


def mask_contacts(text: str, *, default_region: str) -> Masked:
    """Mask emails, then links, then phones (so digits inside URLs are never read as phones).

    ``default_region`` is the preferences country (ISO alpha-2, default ``IN``) used to
    read numbers written without a country code.
    """
    emails, links, phones = _Numbering("EMAIL"), _Numbering("LINK"), _Numbering("PHONE")
    masked = _mask_emails(text, emails)
    masked = _mask_links(masked, links)
    masked = _mask_phones(masked, default_region, phones)
    return Masked(
        masked,
        Contacts(tuple(emails.values), tuple(phones.values), tuple(links.values)),
    )


def strip_placeholders(text: str) -> str:
    """Remove placeholders the AI echoed back, with the space in front of each."""
    return _PLACEHOLDER.sub("", text).strip() if "[[" in text else text


__all__ = ["Contacts", "Masked", "mask_contacts", "strip_placeholders"]
