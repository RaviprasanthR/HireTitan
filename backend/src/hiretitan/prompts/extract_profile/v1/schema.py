"""Output schema for ``extract_profile`` v1: a ``ProfileContent`` without contact details.

No email, phone or links (the model never sees them, FR-008a) and no item ids (assigned after
validation). Every field is required but may be null, which OpenAI strict structured output
needs. ``additionalProperties`` is false everywhere; every string and list is bounded like the
domain types in ``profile/domain/content.py``.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


def text(maximum: int) -> type[str]:
    return Annotated[str, StringConstraints(max_length=maximum)]  # type: ignore[return-value]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class YearMonth(Strict):
    year: int = Field(ge=1950, le=2100)
    month: int | None = Field(ge=1, le=12)


class Contact(Strict):
    name: text(120)  # type: ignore[valid-type]
    location: text(120) | None  # type: ignore[valid-type]


class Experience(Strict):
    employer: text(200)  # type: ignore[valid-type]
    title: text(200)  # type: ignore[valid-type]
    location: text(120) | None  # type: ignore[valid-type]
    start: YearMonth | None
    end: YearMonth | None
    current: bool
    bullets: list[text(500)] = Field(max_length=30)  # type: ignore[valid-type]


class Education(Strict):
    institution: text(200)  # type: ignore[valid-type]
    qualification: text(200) | None  # type: ignore[valid-type]
    field: text(200) | None  # type: ignore[valid-type]
    start: YearMonth | None
    end: YearMonth | None
    grade: text(50) | None  # type: ignore[valid-type]


class Project(Strict):
    name: text(200)  # type: ignore[valid-type]
    description: text(1000) | None  # type: ignore[valid-type]
    technologies: list[text(80)] = Field(max_length=30)  # type: ignore[valid-type]


class Certification(Strict):
    name: text(200)  # type: ignore[valid-type]
    issuer: text(200) | None  # type: ignore[valid-type]
    date: YearMonth | None


class ExtractedProfile(Strict):
    contact: Contact
    headline: text(200) | None  # type: ignore[valid-type]
    summary: text(2000) | None  # type: ignore[valid-type]
    experience: list[Experience] = Field(max_length=40)
    education: list[Education] = Field(max_length=20)
    skills: list[text(80)] = Field(max_length=150)  # type: ignore[valid-type]
    projects: list[Project] = Field(max_length=30)
    certifications: list[Certification] = Field(max_length=30)


# The prompt registry loads the model named ``Output``.
Output = ExtractedProfile
