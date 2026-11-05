"""API models for profile content. They mirror the bounds in data-model.md and accept
incomplete values (drafts are autosaved before the confirm rules are applied)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from hiretitan.profile.domain.content import ProfileContent
from hiretitan.profile.domain.serialization import content_from_json, content_to_json

S40 = Annotated[str, StringConstraints(max_length=40)]
S50 = Annotated[str, StringConstraints(max_length=50)]
S80 = Annotated[str, StringConstraints(max_length=80)]
S100 = Annotated[str, StringConstraints(max_length=100)]
S120 = Annotated[str, StringConstraints(max_length=120)]
S200 = Annotated[str, StringConstraints(max_length=200)]
S254 = Annotated[str, StringConstraints(max_length=254)]
S500 = Annotated[str, StringConstraints(max_length=500)]
S1000 = Annotated[str, StringConstraints(max_length=1000)]
S2000 = Annotated[str, StringConstraints(max_length=2000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class YearMonthModel(Strict):
    year: int = Field(ge=1950, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)


class LinkModel(Strict):
    url: S500
    label: S100 | None = None


class ContactModel(Strict):
    name: S120 = ""
    email: S254 | None = None
    phone: S40 | None = None
    location: S120 | None = None
    links: list[LinkModel] = Field(default_factory=list, max_length=10)


class ExperienceModel(Strict):
    id: UUID | None = None
    employer: S200 = ""
    title: S200 = ""
    location: S120 | None = None
    start: YearMonthModel | None = None
    end: YearMonthModel | None = None
    current: bool = False
    bullets: list[S500] = Field(default_factory=list, max_length=30)


class EducationModel(Strict):
    id: UUID | None = None
    institution: S200 = ""
    qualification: S200 | None = None
    field: S200 | None = None
    start: YearMonthModel | None = None
    end: YearMonthModel | None = None
    grade: S50 | None = None


class ProjectModel(Strict):
    id: UUID | None = None
    name: S200 = ""
    description: S1000 | None = None
    technologies: list[S80] = Field(default_factory=list, max_length=30)
    link: S500 | None = None


class CertificationModel(Strict):
    id: UUID | None = None
    name: S200 = ""
    issuer: S200 | None = None
    date: YearMonthModel | None = None


class ProfileContentModel(Strict):
    contact: ContactModel
    headline: S200 | None = None
    summary: S2000 | None = None
    experience: list[ExperienceModel] = Field(default_factory=list, max_length=40)
    education: list[EducationModel] = Field(default_factory=list, max_length=20)
    skills: list[S80] = Field(default_factory=list, max_length=150)
    projects: list[ProjectModel] = Field(default_factory=list, max_length=30)
    certifications: list[CertificationModel] = Field(default_factory=list, max_length=30)

    def to_domain(self) -> ProfileContent:
        return content_from_json(self.model_dump(mode="json"))

    @classmethod
    def from_domain(cls, content: ProfileContent) -> ProfileContentModel:
        return cls.model_validate(content_to_json(content))

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ProfileContentModel:
        return cls.model_validate(data)
