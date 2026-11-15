"""The resume a person used for a pipeline job (feature 002f): how it is shown, what can be chosen.

Pure. The choice is the person's own record and never an AI input (FR-013); import-linter keeps
the modules that hold it out of the workflow, prompt and LLM paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final, Literal
from uuid import UUID

ChoiceState = Literal["chosen", "removed", "none"]

# A file rejected as "not a resume" is the only one that cannot be chosen. Files still being read,
# or whose reading failed, were uploaded as resumes, so they can (spec edge cases, FR-012).
NOT_OFFERABLE: Final = frozenset({"not_resume"})


@dataclass(frozen=True, slots=True)
class ResumeChoice:
    """What a pipeline job shows for its resume.

    ``chosen``: the stored file (name and the day it was added). ``removed``: the file was
    removed, and its name stays as a plain note. ``none``: no resume.
    """

    state: ChoiceState
    resume_file_id: UUID | None
    name: str | None
    added_on: date | None


def choice_from(
    resume_file_id: UUID | None, resume_name: str | None, resume_added_on: date | None
) -> ResumeChoice:
    """The display rule over the stored columns (data-model.md)."""
    if resume_name is None:
        return ResumeChoice("none", None, None, None)
    state: ChoiceState = "chosen" if resume_file_id is not None else "removed"
    return ResumeChoice(state, resume_file_id, resume_name, resume_added_on)


def offerable(parse_status: str) -> bool:
    """Whether a stored resume file can be chosen for a job (FR-012)."""
    return parse_status not in NOT_OFFERABLE
