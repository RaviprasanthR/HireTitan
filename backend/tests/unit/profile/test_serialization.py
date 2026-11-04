"""T041 support: ProfileContent <-> JSON for the jsonb columns."""

from __future__ import annotations

import json

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


def full() -> ProfileContent:
    return ProfileContent(
        contact=Contact(
            name="Jane Example",
            email="jane@example.com",
            phone="+91 90000 00001",
            location="Pune",
            links=(Link(url="https://github.com/jane-fake", label="GitHub"),),
        ),
        headline="Backend engineer",
        summary="Six years of APIs.",
        experience=(
            Experience(
                employer="Acme",
                title="Engineer",
                start=YearMonth(2021, 1),
                current=True,
                location="Remote",
                bullets=("Built X", "Led Y"),
            ),
        ),
        education=(
            Education(
                institution="Example Institute",
                qualification="B.Tech",
                field_of_study="CS",
                start=YearMonth(2013),
                end=YearMonth(2017, 5),
                grade="8.1 CGPA",
            ),
        ),
        skills=("Python", "Go"),
        projects=(Project(name="Tracer", description="d", technologies=("Rust",), link="x"),),
        certifications=(Certification(name="AWS Dev", issuer="AWS", date=YearMonth(2022)),),
    )


def test_roundtrip_is_lossless_including_ids() -> None:
    original = full()
    assert content_from_json(content_to_json(original)) == original


def test_output_is_plain_json() -> None:
    data = content_to_json(full())
    assert json.loads(json.dumps(data)) == data
    assert data["experience"][0]["start"] == {"year": 2021, "month": 1}
    assert isinstance(data["experience"][0]["id"], str)


def test_missing_optional_parts_use_defaults() -> None:
    content = content_from_json({"contact": {"name": "Only Name"}})
    assert content == ProfileContent(contact=Contact(name="Only Name"))


def test_dates_without_month_roundtrip() -> None:
    content = ProfileContent(
        contact=Contact(name="A"), education=(Education(institution="U", start=YearMonth(2013)),)
    )
    again = content_from_json(content_to_json(content))
    assert again.education[0].start == YearMonth(2013, None)
