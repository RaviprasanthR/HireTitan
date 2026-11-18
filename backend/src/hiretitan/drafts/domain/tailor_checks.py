"""Truthfulness checks for a tailored resume's AI choice (research R4, R5). Pure.

The AI may reword a bullet of the profile, but every number and technology term in the new bullet
must already be in the bullet it came from, and every id and skill must exist in the profile.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from typing import Final

from hiretitan.drafts.domain.checks import Problem, TechTerms, check_text
from hiretitan.drafts.domain.facts import Fact
from hiretitan.drafts.domain.profile_view import ProfileView
from hiretitan.drafts.domain.resume_doc import ResumeChoice

_NUMBER: Final = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")


def _term_in(text: str, term: str) -> bool:
    return (
        re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, re.IGNORECASE)
        is not None
    )


def check_choice(
    choice: ResumeChoice,
    profile: ProfileView,
    facts: tuple[Fact, ...],
    *,
    tech_terms: TechTerms,
    allowed_names: Collection[str],
    years: int | None,
    context: str,
) -> list[Problem]:
    problems: list[Problem] = []
    jobs = {job.id: job for job in profile.experience}
    for item in choice.experience:
        job = jobs.get(item.experience_id)
        if job is None:
            problems.append(Problem("unknown_experience", f"{item.experience_id} is not a job."))
            continue
        for bullet in item.bullets:
            if not 0 <= bullet.source_index < len(job.bullets):
                problems.append(
                    Problem("unknown_bullet", f"Bullet {bullet.source_index} of {job.employer}.")
                )
                continue
            source = job.bullets[bullet.source_index]
            # names (employers, schools, clients) only from the profile, the job or this bullet
            problems += [
                p
                for p in check_text(
                    bullet.text,
                    (),
                    facts,
                    tech_terms=tech_terms,
                    allowed_names=(*allowed_names, source),
                    years=years,
                    context=context,
                )
                if p.code == "name"
            ]
            for number in _NUMBER.findall(bullet.text):
                if number not in _NUMBER.findall(source):
                    problems.append(
                        Problem("number", f"The number {number} is not in the original bullet.")
                    )
            for name, aliases in tech_terms:
                for term in (name, *aliases):
                    if _term_in(bullet.text, term) and not _term_in(source, term):
                        problems.append(
                            Problem("technology", f"{name} is not in the original bullet.")
                        )
                        break
    own = {" ".join(s.split()).casefold() for s in profile.skills}
    for skill in choice.skills:
        if " ".join(skill.split()).casefold() not in own:
            problems.append(Problem("skill", f"{skill} is not one of your skills."))
    known_projects = {p.id for p in profile.projects}
    for project_id in choice.project_ids:
        if project_id not in known_projects:
            problems.append(Problem("unknown_project", f"{project_id} is not a project."))
    problems += check_text(
        choice.summary,
        (),
        facts,
        tech_terms=tech_terms,
        allowed_names=allowed_names,
        years=years,
        context=context,
    )
    return problems
