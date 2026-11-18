"""The tailored resume document and how it is built from the confirmed profile. Pure.

Everything that identifies the person or a job in it (name, contact details, employer, title,
dates, location, schools, certifications) is copied from the profile by id, never typed by the AI.
The AI only chooses the summary wording, the order and wording of bullets taken from the profile's
own bullets, the order of skills and which projects to show (research R5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from hiretitan.drafts.domain.profile_view import ProfileView, format_ym

SUMMARY_MAX: Final = 1200
BULLET_MAX: Final = 400
Short = Annotated[str, StringConstraints(max_length=300)]
Medium = Annotated[str, StringConstraints(max_length=1200)]
Bullet = Annotated[str, StringConstraints(min_length=1, max_length=BULLET_MAX)]
Skill = Annotated[str, StringConstraints(min_length=1, max_length=80)]
_WORD: Final = re.compile(r"[A-Za-z0-9+#.]+")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocContact(_Strict):
    name: Short
    email: Short | None = None
    phone: Short | None = None
    location: Short | None = None
    links: list[Short] = Field(default_factory=list, max_length=10)


class DocExperience(_Strict):
    id: Short
    employer: Short
    title: Short
    dates: Short = ""
    location: Short | None = None
    bullets: list[Bullet] = Field(default_factory=list, max_length=30)


class DocProject(_Strict):
    id: Short
    name: Short
    description: Medium | None = None
    technologies: list[Skill] = Field(default_factory=list, max_length=30)


class DocEducation(_Strict):
    id: Short
    institution: Short
    detail: Short = ""
    dates: Short = ""


class DocCertification(_Strict):
    id: Short
    name: Short
    issuer: Short | None = None


class ResumeDocument(_Strict):
    contact: DocContact
    headline: Short | None = None
    summary: Annotated[str, StringConstraints(max_length=SUMMARY_MAX)] = ""
    experience: list[DocExperience] = Field(default_factory=list, max_length=40)
    skills: list[Skill] = Field(default_factory=list, max_length=150)
    projects: list[DocProject] = Field(default_factory=list, max_length=30)
    education: list[DocEducation] = Field(default_factory=list, max_length=20)
    certifications: list[DocCertification] = Field(default_factory=list, max_length=30)


@dataclass(frozen=True, slots=True)
class BulletChoice:
    source_index: int
    text: str


@dataclass(frozen=True, slots=True)
class ExperienceChoice:
    experience_id: str
    bullets: tuple[BulletChoice, ...]


@dataclass(frozen=True, slots=True)
class ResumeChoice:
    """What the AI may decide: wording and order, nothing that identifies anything."""

    summary: str
    experience: tuple[ExperienceChoice, ...] = ()
    skills: tuple[str, ...] = ()
    project_ids: tuple[str, ...] = ()


def _dates(
    start: tuple[int, int | None] | None, end: tuple[int, int | None] | None, *, current: bool
) -> str:
    left = format_ym(start)
    right = "Present" if current else format_ym(end)
    return " - ".join(part for part in (left, right) if part)


def build_from_profile(profile: ProfileView, choice: ResumeChoice) -> ResumeDocument:
    """The document: profile facts copied by id, the choice's wording where it names a known id."""
    by_exp = {c.experience_id: c for c in choice.experience}
    experience: list[DocExperience] = []
    for job in profile.experience:
        picked = by_exp.get(job.id)
        if picked is not None:
            bullets = [b.text.strip() for b in picked.bullets if b.text.strip()]
        else:
            bullets = [b.strip() for b in job.bullets if b.strip()]
        experience.append(
            DocExperience(
                id=job.id,
                employer=job.employer,
                title=job.title,
                dates=_dates(job.start, job.end, current=job.current),
                location=job.location,
                bullets=[b[:BULLET_MAX] for b in bullets],
            )
        )
    own = {" ".join(s.split()).casefold(): s for s in profile.skills}
    skills = []
    for wanted in choice.skills:
        key = " ".join(wanted.split()).casefold()
        if key in own and own[key] not in skills:
            skills.append(own[key])
    skills += [s for s in profile.skills if s not in skills]
    shown = set(choice.project_ids) if choice.project_ids else {p.id for p in profile.projects}
    projects = [
        DocProject(
            id=p.id, name=p.name, description=p.description, technologies=list(p.technologies)
        )
        for p in profile.projects
        if p.id in shown
    ]
    education = [
        DocEducation(
            id=e.id,
            institution=e.institution,
            detail=", ".join(x for x in (e.qualification, e.field_of_study) if x),
            dates=_dates(e.start, e.end, current=False),
        )
        for e in profile.education
    ]
    certs = [
        DocCertification(id=c.id, name=c.name, issuer=c.issuer) for c in profile.certifications
    ]
    contact = profile.contact
    return ResumeDocument(
        contact=DocContact(
            name=contact.name,
            email=contact.email,
            phone=contact.phone,
            location=contact.location,
            links=list(contact.links),
        ),
        headline=profile.headline,
        summary=choice.summary.strip()[:SUMMARY_MAX],
        experience=experience,
        skills=skills,
        projects=projects,
        education=education,
        certifications=certs,
    )


def _score(text: str, words: set[str]) -> int:
    return len({w.casefold() for w in _WORD.findall(text)} & words)


def plain_reorder(profile: ProfileView, keywords: list[str]) -> ResumeDocument:
    """The fallback: the profile's own wording, ordered by how well it matches the job."""
    words = {w.casefold() for keyword in keywords for w in _WORD.findall(keyword)}

    def ordered(bullets: tuple[str, ...]) -> tuple[BulletChoice, ...]:
        order = sorted(range(len(bullets)), key=lambda i: (-_score(bullets[i], words), i))
        return tuple(BulletChoice(i, bullets[i]) for i in order)

    experience = tuple(ExperienceChoice(job.id, ordered(job.bullets)) for job in profile.experience)
    skills = tuple(sorted(profile.skills, key=lambda skill: -_score(skill, words)))
    summary = (profile.summary or profile.headline or "").strip()
    return build_from_profile(
        profile, ResumeChoice(summary=summary, experience=experience, skills=skills)
    )


BlockKind = Literal["name", "line", "heading", "title", "bullet"]


@dataclass(frozen=True, slots=True)
class Block:
    kind: BlockKind
    text: str


def document_blocks(doc: ResumeDocument) -> list[Block]:
    """The resume as blocks in reading order, one single column. Renderers draw exactly these."""
    blocks = [Block("name", doc.contact.name)]
    if doc.headline:
        blocks.append(Block("line", doc.headline))
    contact = [c for c in (doc.contact.email, doc.contact.phone, doc.contact.location) if c] + list(
        doc.contact.links
    )
    if contact:
        blocks.append(Block("line", " | ".join(contact)))
    if doc.summary.strip():
        blocks += [Block("heading", "Summary"), Block("line", doc.summary.strip())]
    if doc.experience:
        blocks.append(Block("heading", "Experience"))
        for job in doc.experience:
            blocks.append(Block("title", f"{job.title}, {job.employer}"))
            meta = " | ".join(x for x in (job.dates, job.location or "") if x)
            if meta:
                blocks.append(Block("line", meta))
            blocks += [Block("bullet", b) for b in job.bullets]
    if doc.skills:
        blocks += [Block("heading", "Skills"), Block("line", ", ".join(doc.skills))]
    if doc.projects:
        blocks.append(Block("heading", "Projects"))
        for project in doc.projects:
            blocks.append(Block("title", project.name))
            if project.description:
                blocks.append(Block("line", project.description))
            if project.technologies:
                blocks.append(Block("line", ", ".join(project.technologies)))
    if doc.education:
        blocks.append(Block("heading", "Education"))
        for edu in doc.education:
            blocks.append(Block("title", edu.institution))
            meta = " | ".join(x for x in (edu.detail, edu.dates) if x)
            if meta:
                blocks.append(Block("line", meta))
    if doc.certifications:
        blocks.append(Block("heading", "Certifications"))
        for cert in doc.certifications:
            blocks.append(
                Block("line", f"{cert.name} ({cert.issuer})" if cert.issuer else cert.name)
            )
    return blocks


def document_text(doc: ResumeDocument) -> list[str]:
    """The lines of the resume in reading order (used by the keyword match and render tests)."""
    return [b.text for b in document_blocks(doc)]


# characters XML 1.0 cannot hold: python-docx refuses them and the download would fail
_XML_INVALID: Final = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_control(data: Any) -> Any:
    """The same value with control characters (other than tab and line ends) removed."""
    if isinstance(data, str):
        return _XML_INVALID.sub("", data)
    if isinstance(data, list):
        return [strip_control(item) for item in data]
    if isinstance(data, dict):
        return {key: strip_control(value) for key, value in data.items()}
    return data


def document_from_dict(data: Any) -> ResumeDocument:
    """Validate a stored or edited document. Raises ``pydantic.ValidationError``."""
    return ResumeDocument.model_validate(strip_control(data))
