"""Conversions around the AI's output: ``ExtractedProfile`` JSON <-> ``ProfileContent``.

The extraction schema has no contact details and no ids; the domain type has both. Contact
details come back from the masking step, and the items get fresh ids here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from hiretitan.platform.untrusted.mask_contacts import Contacts, strip_placeholders
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
from hiretitan.profile.domain.serialization import content_from_json, content_to_json

MAX_LINKS = 10


def _ym(value: dict[str, Any] | None) -> YearMonth | None:
    return None if value is None else YearMonth(value["year"], value.get("month"))


def _ym_json(value: YearMonth | None) -> dict[str, Any] | None:
    return None if value is None else {"year": value.year, "month": value.month}


def extracted_to_content(data: dict[str, Any]) -> ProfileContent:
    """An ``ExtractedProfile`` dump to domain content, with fresh item ids."""
    return ProfileContent(
        contact=Contact(name=data["contact"]["name"], location=data["contact"].get("location")),
        headline=data.get("headline"),
        summary=data.get("summary"),
        experience=tuple(
            Experience(
                employer=e["employer"],
                title=e["title"],
                location=e.get("location"),
                start=_ym(e.get("start")),
                end=_ym(e.get("end")),
                current=bool(e.get("current")),
                bullets=tuple(e.get("bullets", [])),
            )
            for e in data.get("experience", [])
        ),
        education=tuple(
            Education(
                institution=e["institution"],
                qualification=e.get("qualification"),
                field_of_study=e.get("field"),
                start=_ym(e.get("start")),
                end=_ym(e.get("end")),
                grade=e.get("grade"),
            )
            for e in data.get("education", [])
        ),
        skills=tuple(data.get("skills", [])),
        projects=tuple(
            Project(
                name=p["name"],
                description=p.get("description"),
                technologies=tuple(p.get("technologies", [])),
            )
            for p in data.get("projects", [])
        ),
        certifications=tuple(
            Certification(name=c["name"], issuer=c.get("issuer"), date=_ym(c.get("date")))
            for c in data.get("certifications", [])
        ),
    )


def content_to_extracted(content: ProfileContent) -> dict[str, Any]:
    """Domain content back to the extraction shape (no contact details, no ids)."""
    return {
        "contact": {"name": content.contact.name, "location": content.contact.location},
        "headline": content.headline,
        "summary": content.summary,
        "experience": [
            {
                "employer": e.employer,
                "title": e.title,
                "location": e.location,
                "start": _ym_json(e.start),
                "end": _ym_json(e.end),
                "current": e.current,
                "bullets": list(e.bullets),
            }
            for e in content.experience
        ],
        "education": [
            {
                "institution": e.institution,
                "qualification": e.qualification,
                "field": e.field_of_study,
                "start": _ym_json(e.start),
                "end": _ym_json(e.end),
                "grade": e.grade,
            }
            for e in content.education
        ],
        "skills": list(content.skills),
        "projects": [
            {"name": p.name, "description": p.description, "technologies": list(p.technologies)}
            for p in content.projects
        ],
        "certifications": [
            {"name": c.name, "issuer": c.issuer, "date": _ym_json(c.date)}
            for c in content.certifications
        ],
    }


def _map_strings(value: Any, fn: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, list):
        return [_map_strings(v, fn) for v in value]
    if isinstance(value, dict):
        return {k: v if k == "id" else _map_strings(v, fn) for k, v in value.items()}
    return value


def strip_all_placeholders(content: ProfileContent) -> ProfileContent:
    """Remove ``[[EMAIL_n]]``-style placeholders the model may have echoed, everywhere."""
    return content_from_json(_map_strings(content_to_json(content), strip_placeholders))


def merge_contacts(content: ProfileContent, contacts: Contacts) -> ProfileContent:
    """First email and phone into the contact; links into ``contact.links``."""
    links: Sequence[Link] = tuple(Link(url=u) for u in contacts.links[:MAX_LINKS])
    contact = replace(
        content.contact,
        email=contacts.emails[0] if contacts.emails else None,
        phone=contacts.phones[0] if contacts.phones else None,
        links=tuple(links),
    )
    return replace(content, contact=contact)
