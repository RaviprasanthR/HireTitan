"""Output schema for ``tailor_resume`` v1."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BulletOut(Strict):
    source_index: Annotated[int, Field(ge=0, le=100)]
    text: Annotated[str, StringConstraints(min_length=1, max_length=400)]


class ExperienceOut(Strict):
    experience_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    bullets: list[BulletOut] = Field(max_length=30)


class TailorResumeOutput(Strict):
    summary: Annotated[str, StringConstraints(max_length=1200)]
    experience: list[ExperienceOut] = Field(max_length=40)
    skills: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        max_length=60
    )
    project_ids: list[Annotated[str, StringConstraints(min_length=1, max_length=64)]] = Field(
        max_length=30
    )


# The prompt registry loads the model named ``Output``.
Output = TailorResumeOutput
