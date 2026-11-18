"""Business checks for ``tailor_resume`` v1: the logic lives in ``drafts.domain.tailor_checks``.

``choice_of`` turns the schema output into the domain's ``ResumeChoice``.
"""

from __future__ import annotations

from typing import Any

from hiretitan.drafts.domain.resume_doc import BulletChoice, ExperienceChoice, ResumeChoice


def choice_of(output: Any) -> ResumeChoice:
    return ResumeChoice(
        summary=output.summary,
        experience=tuple(
            ExperienceChoice(
                item.experience_id,
                tuple(BulletChoice(b.source_index, b.text) for b in item.bullets),
            )
            for item in output.experience
        ),
        skills=tuple(output.skills),
        project_ids=tuple(output.project_ids),
    )
