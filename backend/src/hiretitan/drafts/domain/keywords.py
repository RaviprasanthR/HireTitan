"""Which job keywords the person can honestly claim, and how well a resume matches them. Pure."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from hiretitan.drafts.domain.profile_view import ProfileView

_WORD_EDGE: Final = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"
MissingReason = Literal["not_in_profile", "not_in_resume"]


def _mentions(text: str, term: str) -> bool:
    left, right = _WORD_EDGE
    return re.search(left + re.escape(term.strip()) + right, text, re.IGNORECASE) is not None


def profile_text(profile: ProfileView) -> str:
    parts: list[str] = [profile.headline or "", profile.summary or "", *profile.skills]
    for job in profile.experience:
        parts += [job.title, job.employer, *job.bullets]
    for project in profile.projects:
        parts += [project.name, project.description or "", *project.technologies]
    for cert in profile.certifications:
        parts.append(cert.name)
    for edu in profile.education:
        parts += [edu.qualification or "", edu.field_of_study or ""]
    return "\n".join(parts)


def backed(keywords: Iterable[str], profile: ProfileView) -> set[str]:
    """The keywords the profile itself mentions: only these may be worked into the resume."""
    text = profile_text(profile)
    return {k for k in keywords if k.strip() and _mentions(text, k)}


@dataclass(frozen=True, slots=True)
class Missing:
    keyword: str
    reason: MissingReason


@dataclass(frozen=True, slots=True)
class KeywordMatch:
    matched: tuple[str, ...]
    missing: tuple[Missing, ...]
    score: float

    def to_dict(self) -> dict[str, object]:
        return {
            "matched": list(self.matched),
            "missing": [{"keyword": m.keyword, "reason": m.reason} for m in self.missing],
            "score": round(self.score, 3),
        }


def match(
    keywords: Sequence[str], doc_text: Iterable[str], backed_keywords: set[str]
) -> KeywordMatch:
    """Matched = in the resume. Missing = not in it, told apart by whether the profile has it."""
    text = "\n".join(doc_text)
    unique = list(dict.fromkeys(k for k in keywords if k.strip()))
    matched = tuple(k for k in unique if _mentions(text, k))
    missing = tuple(
        Missing(k, "not_in_resume" if k in backed_keywords else "not_in_profile")
        for k in unique
        if k not in matched
    )
    score = len(matched) / len(unique) if unique else 0.0
    return KeywordMatch(matched, missing, score)
