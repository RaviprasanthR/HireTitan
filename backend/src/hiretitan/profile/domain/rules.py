"""Rules a profile must pass to be confirmed (FR-018). Pure.

A draft may be incomplete (FR-016); these rules decide whether it can become a version.
All problems are reported together, each with the path of the field the UI should mark.
"""

from __future__ import annotations

from dataclasses import dataclass

from hiretitan.profile.domain.content import Education, Experience, ProfileContent, YearMonth


@dataclass(frozen=True, slots=True)
class RuleError:
    path: str
    message: str


def _end_before_start(start: YearMonth | None, end: YearMonth | None) -> bool:
    return start is not None and end is not None and end < start


def _experience_errors(index: int, job: Experience) -> list[RuleError]:
    where = f"experience[{index}]"
    errors: list[RuleError] = []
    if not job.employer.strip():
        errors.append(RuleError(f"{where}.employer", "Employer is required"))
    if not job.title.strip():
        errors.append(RuleError(f"{where}.title", "Job title is required"))
    if job.current and job.end is not None:
        errors.append(RuleError(f"{where}.end", "A current job has no end date"))
    elif _end_before_start(job.start, job.end):
        errors.append(RuleError(f"{where}.end", "End date is before the start date"))
    return errors


def _education_errors(index: int, entry: Education) -> list[RuleError]:
    where = f"education[{index}]"
    errors: list[RuleError] = []
    if not entry.institution.strip():
        errors.append(RuleError(f"{where}.institution", "Institution is required"))
    if _end_before_start(entry.start, entry.end):
        errors.append(RuleError(f"{where}.end", "End date is before the start date"))
    return errors


def confirm_errors(content: ProfileContent) -> list[RuleError]:
    """Every reason this profile cannot be confirmed yet; empty means it can."""
    errors: list[RuleError] = []
    if not content.contact.name.strip():
        errors.append(RuleError("contact.name", "Name is required"))
    if not (content.experience or content.education or content.skills):
        errors.append(RuleError("profile", "Add at least one of experience, education or skills"))
    for i, job in enumerate(content.experience):
        errors.extend(_experience_errors(i, job))
    for i, entry in enumerate(content.education):
        errors.extend(_education_errors(i, entry))
    errors.extend(
        RuleError(f"projects[{i}].name", "Project name is required")
        for i, project in enumerate(content.projects)
        if not project.name.strip()
    )
    errors.extend(
        RuleError(f"certifications[{i}].name", "Certification name is required")
        for i, cert in enumerate(content.certifications)
        if not cert.name.strip()
    )
    errors.extend(
        RuleError(f"skills[{i}]", "A skill must not be empty")
        for i, skill in enumerate(content.skills)
        if not skill.strip()
    )
    return errors
