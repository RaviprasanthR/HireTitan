"""A person at a company: field checks and identity keys (feature 002b, FR-006, FR-009, FR-012).

Pure. The same checks serve typed contacts (refused with field errors) and imported ones (the
import drops only the bad field, research R11). Control characters are removed with feature
001's sanitizer; the text is the person's own data and never goes to an AI (FR-022).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from hiretitan.platform.untrusted.sanitize import sanitize

NAME_MAX: Final = 120
ROLE_MAX: Final = 120
LINK_MAX: Final = 500
EMAIL_MAX: Final = 254
CONTACT_NOTE_MAX: Final = 2_000
COMPANY_NOTE_MAX: Final = 5_000
CONFIDENCES: Final = ("high", "medium", "low")

_BARE_HOST: Final = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}(?:[/?#]|$)", re.IGNORECASE)
_EMAIL: Final = re.compile(r"^[^@\s]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$", re.IGNORECASE)
_PHONE: Final = re.compile(r"^[0-9 +()\-]{5,30}$")


@dataclass(frozen=True, slots=True)
class FieldIssue:
    """Same shape as ``search.application.paste.FieldIssue``; the domain cannot import it."""

    field: str
    message: str


@dataclass(frozen=True, slots=True)
class ContactFields:
    name: str
    role: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    confidence: str | None = None
    note: str | None = None


def clean(text: str | None) -> str | None:
    """Strip control characters and surrounding space; empty text becomes ``None``."""
    if text is None:
        return None
    cleaned = sanitize(text).text
    return cleaned or None


def name_key(name: str) -> str:
    """Lower-case, accents and punctuation and spaces removed: who the person is (FR-006)."""
    decomposed = unicodedata.normalize("NFKD", name)
    kept = (ch for ch in decomposed if ch.isalnum() and not unicodedata.combining(ch))
    return "".join(kept).lower()[:NAME_MAX]


def normalize_link(raw: str) -> str | None:
    """The link as stored (``https://`` added to a bare host), or ``None`` if it is not one."""
    text = raw.strip()
    if not text or len(text) > LINK_MAX or any(ch.isspace() for ch in text):
        return None
    if "://" in text:
        candidate = text
    elif _BARE_HOST.match(text):
        candidate = f"https://{text}"
    else:
        return None
    parts = urlsplit(candidate)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    return candidate


def link_key(url: str | None) -> str | None:
    """Host without ``www.`` plus path, lower-case, no scheme, query, fragment or final slash."""
    if not url:
        return None
    normalized = normalize_link(url)
    if normalized is None:
        return None
    parts = urlsplit(normalized)
    host = (parts.hostname or "").removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}".lower()


def _too_long(field: str, label: str, text: str, limit: int) -> FieldIssue | None:
    if len(text) > limit:
        return FieldIssue(field, f"The {label} can be at most {limit} characters.")
    return None


def check_contact(
    *,
    name: str | None,
    role: str | None = None,
    linkedin_url: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    confidence: str | None = None,
    note: str | None = None,
) -> tuple[ContactFields | None, list[FieldIssue]]:
    """Check one contact. Returns the cleaned fields, or ``None`` and every problem found."""
    issues: list[FieldIssue] = []
    name_text = clean(name)
    if name_text is None or not name_key(name_text):
        issues.append(FieldIssue("name", "The contact needs a name."))
    elif issue := _too_long("name", "name", name_text, NAME_MAX):
        issues.append(issue)

    role_text = clean(role)
    if role_text and (issue := _too_long("role", "role", role_text, ROLE_MAX)):
        issues.append(issue)

    link_text = clean(linkedin_url)
    link_value: str | None = None
    if link_text is not None:
        link_value = normalize_link(link_text)
        if link_value is None:
            issues.append(FieldIssue("linkedin_url", "The link must be a web address."))

    email_text = clean(email)
    if email_text is not None and (len(email_text) > EMAIL_MAX or not _EMAIL.match(email_text)):
        issues.append(FieldIssue("email", "That does not look like an email address."))

    phone_text = clean(phone)
    if phone_text is not None and not _PHONE.match(phone_text):
        issues.append(
            FieldIssue("phone", "A phone number is 5 to 30 digits, spaces, + - or brackets.")
        )

    confidence_text = (clean(confidence) or "").lower() or None
    if confidence_text is not None and confidence_text not in CONFIDENCES:
        issues.append(FieldIssue("confidence", "Confidence is high, medium or low."))

    note_text = clean(note)
    if note_text and (issue := _too_long("note", "note", note_text, CONTACT_NOTE_MAX)):
        issues.append(issue)

    if issues or name_text is None:
        return None, issues
    return (
        ContactFields(
            name=name_text,
            role=role_text,
            linkedin_url=link_value,
            email=email_text,
            phone=phone_text,
            confidence=confidence_text,
            note=note_text,
        ),
        [],
    )


def check_company_note(body: str | None) -> tuple[str | None, list[FieldIssue]]:
    """The note on a company: empty means "no note"; too long is refused (FR-010)."""
    text = clean(body)
    if text is None:
        return None, []
    if issue := _too_long("body", "note", text, COMPANY_NOTE_MAX):
        return None, [issue]
    return text, []
