"""Synthetic profile and job data for the drafts tests. Nobody real: every name is made up."""

from __future__ import annotations

from hiretitan.drafts.domain.profile_view import (
    CertificationView,
    ContactView,
    EducationView,
    ExperienceView,
    ProfileView,
    ProjectView,
)

EXP_A = "11111111-1111-4111-8111-111111111111"
EXP_B = "22222222-2222-4222-8222-222222222222"

TECH_TERMS = (
    ("Python", ()),
    ("Java", ()),
    ("Kubernetes", ("k8s",)),
    ("PostgreSQL", ("postgres",)),
    ("Django", ()),
    ("Rust", ()),
)


def synthetic_profile(name: str = "Sam Rivera") -> ProfileView:
    return ProfileView(
        contact=ContactView(
            name=name,
            email="sam.rivera@example.invalid",
            phone="+1 555 0100",
            location="Springfield",
            links=("https://example.invalid/in/sam-rivera",),
        ),
        headline="Backend engineer",
        summary="Backend engineer who builds reliable APIs in Python.",
        experience=(
            ExperienceView(
                id=EXP_A,
                employer="Northwind Labs",
                title="Backend Engineer",
                start=(2021, 3),
                end=None,
                current=True,
                location="Springfield",
                bullets=(
                    "Built a Python service handling 40 requests per second",
                    "Moved a PostgreSQL schema to partitioned tables",
                ),
            ),
            ExperienceView(
                id=EXP_B,
                employer="Initech Works",
                title="Junior Developer",
                start=(2019, 1),
                end=(2021, 2),
                bullets=("Wrote Django views and tests",),
            ),
        ),
        education=(
            EducationView(
                id="33333333-3333-4333-8333-333333333333",
                institution="Lakeside University",
                qualification="BSc",
                field_of_study="Computer Science",
                start=(2015, None),
                end=(2019, None),
            ),
        ),
        skills=("Python", "PostgreSQL", "Django"),
        projects=(
            ProjectView(
                id="44444444-4444-4444-8444-444444444444",
                name="Budget Tracker",
                description="A small expense tracker",
                technologies=("Python",),
            ),
        ),
        certifications=(
            CertificationView(
                id="55555555-5555-4555-8555-555555555555", name="Cloud Basics", issuer="Skillhub"
            ),
        ),
    )
