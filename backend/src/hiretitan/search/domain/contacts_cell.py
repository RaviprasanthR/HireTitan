"""The contacts cell of a company sheet: parse it, and write it back (feature 002b; research R3).

Pure and deterministic (no AI: contacts never reach one, FR-022). One cell holds several people,
one per line group::

    Jane Example - Recruiter [High]
    https://www.linkedin.com/in/jane-example
    email: jane@example.com
    phone: +91 98765 43210
    note: Replies fast.

Every line ends up somewhere (FR-005): a field of the person above it, a note line on that
person, or ``leftover`` text the importer keeps as a company note. ``render`` writes the same
grammar, so an export with contacts imports back unchanged (FR-024).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from hiretitan.search.domain.contacts import normalize_link

MAX_PEOPLE: Final = 20
_TAG: Final = re.compile(r"\[\s*(high|med|medium|low)\s*\]", re.IGNORECASE)
_CONFIDENCE: Final = {"high": "high", "med": "medium", "medium": "medium", "low": "low"}
_TAG_TEXT: Final = {"high": "High", "medium": "Med", "low": "Low"}
_URL_LINE: Final = re.compile(r"^(?:https?://\S+|(?:www\.)?linkedin\.com/\S*)$", re.IGNORECASE)
_LABEL: Final = re.compile(r"^(e-?mail|phone|tel|note)\s*:\s*(.+)$", re.IGNORECASE)
_SEPARATORS: Final = (" - ", " – ", " — ", ",", "(")  # noqa: RUF001 (en and em dash are separators on purpose)
_NAME_CONNECTORS: Final = frozenset(
    {"de", "da", "di", "du", "van", "von", "der", "den", "la", "le", "bin", "al", "el", "dos"}
)
_NAME_WORDS_WITH_SIGNAL: Final = 5
_NAME_WORDS_WITHOUT_SIGNAL: Final = 6


@dataclass(frozen=True, slots=True)
class ParsedContact:
    name: str
    role: str | None = None
    confidence: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedCell:
    contacts: tuple[ParsedContact, ...] = ()
    leftover: tuple[str, ...] = ()
    shortened: bool = False


@dataclass(slots=True)
class _Person:
    name: str
    role: str | None
    confidence: str | None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: list[str] | None = None

    def add_note(self, line: str) -> None:
        if self.notes is None:
            self.notes = []
        self.notes.append(line)

    def freeze(self) -> ParsedContact:
        note = "\n".join(self.notes) if self.notes else None
        return ParsedContact(
            self.name, self.role, self.confidence, self.linkedin_url, self.email, self.phone, note
        )


def _looks_like_name(name: str, limit: int) -> bool:
    words = name.split()
    if not words or len(words) > limit or any(ch in name for ch in ":;!"):
        return False
    return all(w[0].isupper() or w.lower() in _NAME_CONNECTORS for w in words)


def _split_person(line: str) -> tuple[str, str | None, str | None] | None:
    """``(name, role, confidence)`` if the line reads like a person, else ``None``."""
    confidence: str | None = None
    if match := _TAG.search(line):
        confidence = _CONFIDENCE[match.group(1).lower()]
        line = _TAG.sub(" ", line)
    line = " ".join(line.split())
    cuts = [(line.find(sep), sep) for sep in _SEPARATORS if line.find(sep) > 0]
    if cuts:
        position, separator = min(cuts)
        name = line[:position].strip()
        role = line[position + len(separator) :].strip().rstrip(")").strip() or None
    else:
        name, role = line, None
    signal = bool(cuts) or confidence is not None
    limit = _NAME_WORDS_WITH_SIGNAL if signal else _NAME_WORDS_WITHOUT_SIGNAL
    if not _looks_like_name(name, limit):
        return None
    return name, role, confidence


def _set_labelled(person: _Person, label: str, value: str) -> None:
    kind = label.lower()
    if kind == "note":
        person.add_note(value)
    elif kind.startswith("e") and person.email is None:
        person.email = value
    elif kind in ("phone", "tel") and person.phone is None:
        person.phone = value
    else:
        person.add_note(f"{kind}: {value}")


def parse(cell: str) -> ParsedCell:
    people: list[_Person] = []
    leftover: list[str] = []
    current: _Person | None = None
    skipping = False  # lines that belong to a person beyond the 20th are dropped with them
    shortened = False

    for raw in cell.splitlines():
        line = raw.strip()
        if not line:
            continue
        link = normalize_link(line) if _URL_LINE.match(line) else None
        labelled = _LABEL.match(line)
        if link is not None:
            if current is None:
                if not skipping:
                    leftover.append(line)
            elif current.linkedin_url is None:
                current.linkedin_url = link
            else:
                current.add_note(link)
        elif labelled is not None:
            if current is not None:
                _set_labelled(current, labelled.group(1), labelled.group(2).strip())
            elif not skipping:
                leftover.append(line)
        elif (person := _split_person(line)) is not None:
            if len(people) >= MAX_PEOPLE:
                shortened = True
                skipping = True
                current = None
            else:
                skipping = False
                current = _Person(*person)
                people.append(current)
        elif current is not None:
            current.add_note(line)
        elif not skipping:
            leftover.append(line)

    return ParsedCell(tuple(p.freeze() for p in people), tuple(leftover), shortened)


def render(contacts: Iterable[ParsedContact]) -> str:
    """Write contacts in the grammar ``parse`` reads, so an export imports back (FR-024)."""
    lines: list[str] = []
    for contact in contacts:
        head = contact.name if not contact.role else f"{contact.name} - {contact.role}"
        if contact.confidence:
            head += f" [{_TAG_TEXT[contact.confidence]}]"
        lines.append(head)
        if contact.linkedin_url:
            lines.append(contact.linkedin_url)
        if contact.email:
            lines.append(f"email: {contact.email}")
        if contact.phone:
            lines.append(f"phone: {contact.phone}")
        if contact.note:
            lines.extend(f"note: {part}" for part in contact.note.splitlines() if part.strip())
    return "\n".join(lines)
