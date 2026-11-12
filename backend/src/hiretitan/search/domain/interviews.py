"""Interview tracking rules (feature 002e): field checks, round numbers and the status column.

Pure. The checks serve typed input only; the person's own notes are never an AI input (FR-010),
and import-linter keeps this module out of the workflow, prompt and LLM paths.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from hiretitan.search.domain.contacts import ContactFields, FieldIssue, clean
from hiretitan.search.domain.contacts import check_contact as _check_contact

ROUND_KINDS: Final = ("screening", "technical", "hr", "managerial", "other")
ROUND_STATES: Final = ("scheduled", "cleared", "failed")
SOURCES: Final = ("direct", "hiring_firm")

FIRM_MAX: Final = 120
INTERVIEWERS_MAX: Final = 300
QUESTION_MAX: Final = 2_000
ANSWER_MAX: Final = 10_000
FEEDBACK_MAX: Final = 10_000


@dataclass(frozen=True, slots=True)
class RoundSummary:
    """What the status column needs of one round."""

    number: int
    state: str


def check_contact(
    *,
    name: str | None,
    role: str | None = None,
    linkedin_url: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> tuple[ContactFields | None, list[FieldIssue]]:
    """The point of contact for one application: the same checks as a company contact."""
    return _check_contact(name=name, role=role, linkedin_url=linkedin_url, email=email, phone=phone)


def check_source(
    kind: str | None, firm_name: str | None
) -> tuple[tuple[str | None, str | None] | None, list[FieldIssue]]:
    """How the job came: ``(kind, firm)``; a firm name is kept only for a hiring firm (FR-003)."""
    if kind is None:
        return (None, None), []
    if kind not in SOURCES:
        return None, [FieldIssue("kind", "The source is direct or through a hiring firm.")]
    if kind == "direct":
        return ("direct", None), []
    firm = clean(firm_name)
    if firm is None:
        return None, [FieldIssue("firm_name", "A hiring firm needs a name.")]
    if len(firm) > FIRM_MAX:
        return None, [
            FieldIssue("firm_name", f"The firm name can be at most {FIRM_MAX} characters.")
        ]
    return ("hiring_firm", firm), []


def check_round_text(
    field: str, text: str | None, limit: int
) -> tuple[str | None, list[FieldIssue]]:
    """Free text on a round: cleaned (line breaks kept), empty becomes ``None``, long is refused."""
    cleaned = clean(text)
    if cleaned is None:
        return None, []
    if len(cleaned) > limit:
        return None, [FieldIssue(field, f"The {field} can be at most {limit} characters.")]
    return cleaned, []


def next_round_number(numbers: Iterable[int]) -> int:
    """Rounds are numbered in the order added; deleting never renumbers (research R3)."""
    return max(numbers, default=0) + 1


def can_add_round(states: Iterable[str]) -> bool:
    """A failed round ends the process, so no new round until it is changed (FR-006)."""
    return "failed" not in states


def status_summary(job_state: str, rounds: Iterable[RoundSummary]) -> tuple[str, int | None]:
    """The status column (FR-007): a failed round wins, else the latest round, else the job state."""
    ordered = sorted(rounds, key=lambda r: r.number)
    failed = [r.number for r in ordered if r.state == "failed"]
    if failed:
        return "failed", max(failed)
    if ordered:
        latest = ordered[-1]
        return latest.state, latest.number
    return job_state, None
