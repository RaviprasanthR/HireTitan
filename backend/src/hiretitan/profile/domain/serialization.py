"""ProfileContent <-> plain JSON (for jsonb columns and the API). Pure."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from hiretitan.profile.domain.content import (
    Certification,
    Contact,
    Education,
    Experience,
    Link,
    ProfileContent,
    Project,
    YearMonth,
)

Json = dict[str, Any]


def _ym_to(value: YearMonth | None) -> Json | None:
    return None if value is None else {"year": value.year, "month": value.month}


def _ym_from(value: Json | None) -> YearMonth | None:
    return None if value is None else YearMonth(value["year"], value.get("month"))


def _id_from(data: Json) -> UUID:
    return UUID(data["id"]) if data.get("id") else uuid4()


def content_to_json(content: ProfileContent) -> Json:
    c = content.contact
    return {
        "contact": {
            "name": c.name,
            "email": c.email,
            "phone": c.phone,
            "location": c.location,
            "links": [{"url": link.url, "label": link.label} for link in c.links],
        },
        "headline": content.headline,
        "summary": content.summary,
        "experience": [
            {
                "id": str(e.id),
                "employer": e.employer,
                "title": e.title,
                "location": e.location,
                "start": _ym_to(e.start),
                "end": _ym_to(e.end),
                "current": e.current,
                "bullets": list(e.bullets),
            }
            for e in content.experience
        ],
        "education": [
            {
                "id": str(e.id),
                "institution": e.institution,
                "qualification": e.qualification,
                "field": e.field_of_study,
                "start": _ym_to(e.start),
                "end": _ym_to(e.end),
                "grade": e.grade,
            }
            for e in content.education
        ],
        "skills": list(content.skills),
        "projects": [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "technologies": list(p.technologies),
                "link": p.link,
            }
            for p in content.projects
        ],
        "certifications": [
            {"id": str(c.id), "name": c.name, "issuer": c.issuer, "date": _ym_to(c.date)}
            for c in content.certifications
        ],
    }


def content_from_json(data: Json) -> ProfileContent:
    c = data["contact"]
    return ProfileContent(
        contact=Contact(
            name=c.get("name", ""),
            email=c.get("email"),
            phone=c.get("phone"),
            location=c.get("location"),
            links=tuple(Link(url=x["url"], label=x.get("label")) for x in c.get("links", [])),
        ),
        headline=data.get("headline"),
        summary=data.get("summary"),
        experience=tuple(
            Experience(
                id=_id_from(e),
                employer=e.get("employer", ""),
                title=e.get("title", ""),
                location=e.get("location"),
                start=_ym_from(e.get("start")),
                end=_ym_from(e.get("end")),
                current=bool(e.get("current", False)),
                bullets=tuple(e.get("bullets", [])),
            )
            for e in data.get("experience", [])
        ),
        education=tuple(
            Education(
                id=_id_from(e),
                institution=e.get("institution", ""),
                qualification=e.get("qualification"),
                field_of_study=e.get("field"),
                start=_ym_from(e.get("start")),
                end=_ym_from(e.get("end")),
                grade=e.get("grade"),
            )
            for e in data.get("education", [])
        ),
        skills=tuple(data.get("skills", [])),
        projects=tuple(
            Project(
                id=_id_from(p),
                name=p.get("name", ""),
                description=p.get("description"),
                technologies=tuple(p.get("technologies", [])),
                link=p.get("link"),
            )
            for p in data.get("projects", [])
        ),
        certifications=tuple(
            Certification(
                id=_id_from(c),
                name=c.get("name", ""),
                issuer=c.get("issuer"),
                date=_ym_from(c.get("date")),
            )
            for c in data.get("certifications", [])
        ),
    )
