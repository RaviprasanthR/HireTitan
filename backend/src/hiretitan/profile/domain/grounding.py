"""Grounding check (FR-011, SC-004, research R5). Pure and deterministic.

Anything the AI extracted that the resume does not support is dropped and reported; the
profile only ever keeps facts found in the user's own text (constitution II).

* skills, employers, titles, institutions, certification and project names: the normalized
  value must be a substring of the normalized source;
* dates: must match a date token in the source ("Jan 2021", "01/2021", "2021");
  ``current`` needs "Present"/"Current" (or similar) in the source;
* bullets: a source line (or up to three wrapped lines) with ``token_set_ratio >= 92``, and
  every number in the bullet must appear in the source;
* summary: ``partial_ratio >= 90`` against the source.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Final

from rapidfuzz import fuzz

from hiretitan.profile.domain.content import (
    Certification,
    Education,
    Experience,
    ProfileContent,
    Project,
    YearMonth,
)

NOT_FOUND: Final = "not found in your resume"
SUMMARY_NOT_FOUND: Final = "summary not found in your resume"
BULLET_THRESHOLD: Final = 92
SUMMARY_THRESHOLD: Final = 90
MAX_WRAPPED_LINES: Final = 3

_KEEP = r"a-z0-9+#."
_PUNCT = re.compile(rf"[^{_KEEP}\s]|(?<![{_KEEP}])\.|\.(?![{_KEEP}])")
_SPACES = re.compile(r"\s+")
_MONTHS: Final = {
    name: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}
_MONTH_YEAR = re.compile(r"\b(" + "|".join(_MONTHS) + r")\.?,?\s+((?:19|20|21)\d\d)\b")
_NUMERIC_MONTH_YEAR = re.compile(r"\b(\d{1,2})\s*[/.-]\s*((?:19|20|21)\d\d)\b")
_ISO_MONTH_YEAR = re.compile(r"\b((?:19|20|21)\d\d)\s*-\s*(\d{1,2})\b")
_YEAR = re.compile(r"\b((?:19|20|21)\d\d)\b")
_NUMBER = re.compile(r"[₹$€£]?\d[\d,]*(?:\.\d+)?(?:%|x\b|k\b|m\b|l\b)?", re.IGNORECASE)
_CURRENT_WORDS = re.compile(r"\b(present|current|currently|ongoing|till date|to date|now)\b")


@dataclass(frozen=True, slots=True)
class DroppedItem:
    path: str
    value: str
    reason: str


@dataclass(frozen=True, slots=True)
class GroundingResult:
    profile: ProfileContent
    dropped: list[DroppedItem]


def normalize(text: str) -> str:
    """NFKC, casefold, punctuation (except ``+ # .``) to spaces, whitespace collapsed."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return _SPACES.sub(" ", _PUNCT.sub(" ", folded)).strip()


class _Source:
    def __init__(self, text: str) -> None:
        raw = unicodedata.normalize("NFKC", text)
        self.normalized = normalize(raw)
        self.padded = f" {self.normalized} "
        lines = [normalize(line) for line in raw.splitlines()]
        self.lines = [line for line in lines if line]
        self.windows = self._windows(self.lines)
        self.numbers = raw.replace(",", "").casefold()
        self.raw_lines = raw.casefold().splitlines()
        self.years, self.months = self._dates(raw.casefold())

    @staticmethod
    def _windows(lines: list[str]) -> list[str]:
        out: list[str] = []
        for size in range(1, MAX_WRAPPED_LINES + 1):
            out.extend(" ".join(lines[i : i + size]) for i in range(len(lines) - size + 1))
        return out

    @staticmethod
    def _dates(text: str) -> tuple[set[int], set[tuple[int, int]]]:
        months: set[tuple[int, int]] = set()
        for m in _MONTH_YEAR.finditer(text):
            months.add((int(m.group(2)), _MONTHS[m.group(1)]))
        for m in _NUMERIC_MONTH_YEAR.finditer(text):
            if 1 <= int(m.group(1)) <= 12:
                months.add((int(m.group(2)), int(m.group(1))))
        for m in _ISO_MONTH_YEAR.finditer(text):
            if 1 <= int(m.group(2)) <= 12:
                months.add((int(m.group(1)), int(m.group(2))))
        years = {int(m.group(1)) for m in _YEAR.finditer(text)}
        return years, months

    def contains(self, value: str) -> bool:
        needle = normalize(value)
        return bool(needle) and f" {needle} " in self.padded

    def current_near(self, employer: str) -> bool:
        """\"Present\"/\"Current\" on the employer's own line or the line after it."""
        needle = normalize(employer)
        for i, line in enumerate(self.raw_lines):
            if needle and needle in normalize(line):
                nearby = " ".join(self.raw_lines[i : i + 2])
                if _CURRENT_WORDS.search(nearby):
                    return True
        return False

    def has_date(self, date: YearMonth) -> bool:
        if date.month is None:
            return date.year in self.years
        return (date.year, date.month) in self.months

    def numbers_present(self, bullet: str) -> bool:
        for match in _NUMBER.finditer(bullet):
            token = match.group(0).replace(",", "").casefold()
            if token not in self.numbers:
                return False
        return True

    def bullet_found(self, bullet: str) -> bool:
        wanted = normalize(bullet)
        if not wanted or not self.numbers_present(bullet):
            return False
        return any(
            fuzz.token_set_ratio(wanted, window) >= BULLET_THRESHOLD for window in self.windows
        )

    def summary_found(self, summary: str) -> bool:
        wanted = normalize(summary)
        return bool(wanted) and fuzz.partial_ratio(wanted, self.normalized) >= SUMMARY_THRESHOLD


def _date_text(date: YearMonth) -> str:
    return f"{date.year}" if date.month is None else f"{date.year}-{date.month:02d}"


class _Grounder:
    def __init__(self, source: _Source) -> None:
        self.source = source
        self.dropped: list[DroppedItem] = []

    def drop(self, path: str, value: str, reason: str = NOT_FOUND) -> None:
        self.dropped.append(DroppedItem(path, value, reason))

    def date(self, path: str, date: YearMonth | None) -> YearMonth | None:
        if date is None or self.source.has_date(date):
            return date
        self.drop(path, _date_text(date))
        return None

    def strings(self, path: str, values: tuple[str, ...]) -> tuple[str, ...]:
        kept: list[str] = []
        for i, value in enumerate(values):
            if self.source.contains(value):
                kept.append(value)
            else:
                self.drop(f"{path}[{i}]", value)
        return tuple(kept)

    def experience(self, i: int, job: Experience) -> Experience | None:
        path = f"experience[{i}]"
        if not (self.source.contains(job.employer) and self.source.contains(job.title)):
            self.drop(path, f"{job.employer} | {job.title}")
            return None
        current = job.current
        if current and not self.source.current_near(job.employer):
            self.drop(f"{path}.current", "current")
            current = False
        bullets: list[str] = []
        for j, bullet in enumerate(job.bullets):
            if self.source.bullet_found(bullet):
                bullets.append(bullet)
            else:
                self.drop(f"{path}.bullets[{j}]", bullet)
        return replace(
            job,
            start=self.date(f"{path}.start", job.start),
            end=self.date(f"{path}.end", job.end),
            current=current,
            bullets=tuple(bullets),
        )

    def education(self, i: int, entry: Education) -> Education | None:
        path = f"education[{i}]"
        if not self.source.contains(entry.institution):
            self.drop(path, entry.institution)
            return None
        qualification = entry.qualification
        if qualification and not self.source.contains(qualification):
            self.drop(f"{path}.qualification", qualification)
            qualification = None
        return replace(
            entry,
            qualification=qualification,
            start=self.date(f"{path}.start", entry.start),
            end=self.date(f"{path}.end", entry.end),
        )

    def project(self, i: int, project: Project) -> Project | None:
        path = f"projects[{i}]"
        if not self.source.contains(project.name):
            self.drop(path, project.name)
            return None
        description = project.description
        if description and not self.source.bullet_found(description):
            self.drop(f"{path}.description", description)
            description = None
        return replace(
            project,
            description=description,
            technologies=self.strings(f"{path}.technologies", project.technologies),
        )

    def certification(self, i: int, cert: Certification) -> Certification | None:
        path = f"certifications[{i}]"
        if not self.source.contains(cert.name):
            self.drop(path, cert.name)
            return None
        return replace(cert, date=self.date(f"{path}.date", cert.date))


def ground(content: ProfileContent, source_text: str) -> GroundingResult:
    """Return the profile with unsupported facts removed, and what was removed."""
    g = _Grounder(_Source(source_text))
    summary = content.summary
    if summary and not g.source.summary_found(summary):
        g.drop("summary", summary, SUMMARY_NOT_FOUND)
        summary = None
    experience = (g.experience(i, x) for i, x in enumerate(content.experience))
    education = (g.education(i, x) for i, x in enumerate(content.education))
    skills = g.strings("skills", content.skills)
    projects = (g.project(i, x) for i, x in enumerate(content.projects))
    certifications = (g.certification(i, x) for i, x in enumerate(content.certifications))
    grounded = ProfileContent(
        contact=content.contact,
        headline=content.headline,
        summary=summary,
        experience=tuple(item for item in experience if item is not None),
        education=tuple(item for item in education if item is not None),
        skills=skills,
        projects=tuple(item for item in projects if item is not None),
        certifications=tuple(item for item in certifications if item is not None),
    )
    return GroundingResult(grounded, g.dropped)
