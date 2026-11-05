"""Generate the 15 eval documents (11 resumes, 4 that are not) and their ``expected/*.yaml``.

T051, reusing the T033 generator.

Run from ``backend/``:  ``uv run python -m evals.extract_profile.cases``
Every identity is fake (``example.*`` emails, ``+91 90000 0000x`` phones). Output is deterministic.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parents[1] / "tests" / "fixtures" / "resumes"
sys.path.insert(0, str(FIXTURES))
import generate as g  # noqa: E402  (the T033 generator)

CASES_DIR = HERE / "cases"
EXPECTED_DIR = HERE / "expected"

SENIOR_JOBS: list[dict[str, Any]] = [
    {
        "employer": "Hooli Systems",
        "title": "Principal Engineer",
        "dates": "Mar 2019 - Present",
        "bullets": [
            "Set the technical direction for a payments platform used by 40 teams",
            "Cut cloud spend by 25% through capacity planning and right-sizing",
        ],
    },
    {
        "employer": "Initech Labs",
        "title": "Senior Engineer",
        "dates": "Aug 2014 - Feb 2019",
        "bullets": [
            "Built an event pipeline processing 50M messages a day on Kafka",
            "Mentored 6 engineers, two of whom were promoted to senior",
        ],
    },
    {
        "employer": "Umbrella Soft",
        "title": "Engineer",
        "dates": "Jul 2009 - Jul 2014",
        "bullets": ["Developed order management features in Java", "Owned the release process"],
    },
]
SENIOR: dict[str, Any] = {
    "name": "Priya Sample",
    "contact": "priya.sample@example.com | +91 90000 00004",
    "location": "Bengaluru, India",
    "education": ("Sample University of Technology", "B.E. Computer Science", "2005 - 2009"),
    "skills": ["Java", "Kotlin", "Kubernetes", "AWS", "Kafka"],
}
FRESHER: dict[str, Any] = {
    "name": "Sam Sample",
    "contact": "sam.sample@example.org | +91 90000 00002",
    "education": (
        "Example Institute of Technology",
        "B.Tech Information Technology",
        "2021 - 2025",
    ),
    "skills": ["Python", "Java", "SQL", "Git"],
    "project": ("Library Tracker", "a small web app for a college library"),
}
Dates = dict[str, tuple[str, str | None]]
MID_DATES: Dates = {"Acme Corp": ("2021-01", None), "Globex Ltd": ("2017-06", "2020-12")}
SENIOR_DATES: Dates = {
    "Hooli Systems": ("2019-03", None),
    "Initech Labs": ("2014-08", "2019-02"),
    "Umbrella Soft": ("2009-07", "2014-07"),
}


def _expected(
    jobs: Sequence[dict[str, Any]],
    dates: Dates,
    *,
    name: str,
    skills: Sequence[str],
    education: Sequence[str],
) -> dict[str, Any]:
    pairs = [dates[str(j["employer"])] for j in jobs]
    return {
        "name": name,
        "employers": [str(j["employer"]) for j in jobs],
        "titles": [str(j["title"]) for j in jobs],
        "dates": sorted({d for pair in pairs for d in pair if d}),
        "skills": list(skills),
        "education": list(education),
    }


NOT_A_RESUME: dict[str, Any] = {
    "is_resume": False,
    "name": "",
    "employers": [],
    "titles": [],
    "dates": [],
    "skills": [],
    "education": [],
}


def _offer_letter_docx(out: Path, filename: str) -> None:
    document = g.new_docx()
    document.add_heading("Globex Ltd", level=0)
    document.add_paragraph("Date: 20 January 2021")
    document.add_heading("Offer of Employment", level=1)
    document.add_paragraph("Dear Rahul Sample,")
    document.add_paragraph(
        "We are pleased to offer you the position of Senior Software Engineer at Globex Ltd. "
        "Your annual cost to company will be INR 24,00,000 and your date of joining will be "
        "1 February 2021. Please sign and return a copy of this letter by 25 January 2021 to "
        "confirm that you accept this offer. This offer is subject to satisfactory background "
        "verification and the terms in the attached employment agreement."
    )
    document.add_paragraph("We look forward to welcoming you to the team.")
    document.add_paragraph("Priya Demo, Human Resources Manager, Globex Ltd")
    document.save(str(out / filename))


def _certificate_pdf(out: Path, filename: str) -> None:
    def body(page: g.Page) -> None:
        page.line("Example Academy", size=16, bold=True)
        page.heading("Certificate of Completion")
        page.line("This is to certify that")
        page.line("Rahul Sample", size=18, bold=True)
        page.line("has successfully completed the 40 hour course")
        page.line("Cloud Fundamentals with Python and SQL", size=12, bold=True)
        page.line("and passed the final assessment with a score of 86 percent.")
        page.line("Issued on 14 March 2022. Certificate number EA-2022-00417.")
        page.line("Director of Learning, Example Academy")

    g.pdf(out / filename, body)


def _job_description_pdf(out: Path, filename: str) -> None:
    def body(page: g.Page) -> None:
        page.line("Senior Backend Engineer - Initech Labs", size=16, bold=True)
        page.line("Location: Bengaluru, India (hybrid)")
        page.heading("About the role")
        page.line("You will design and run the services behind our payments platform.")
        page.heading("Requirements")
        page.bullet("5+ years of experience building backend services in Python or Go")
        page.bullet("Strong knowledge of PostgreSQL, Kafka and Docker")
        page.bullet("Experience with Kubernetes and AWS is a plus")
        page.bullet("Bachelor's degree in Computer Science or a related field")
        page.heading("How to apply")
        page.line("Send your resume to careers at the Initech Labs website by 30 November 2026.")

    g.pdf(out / filename, body)


def _senior_docx(out: Path, filename: str) -> None:
    document = g.new_docx()
    document.add_heading(SENIOR["name"], level=0)
    document.add_paragraph(SENIOR["contact"])
    document.add_paragraph(SENIOR["location"])
    document.add_heading("Experience", level=1)
    for job in SENIOR_JOBS:
        document.add_paragraph(f"{job['employer']} - {job['title']}    {job['dates']}")
        for bullet in job["bullets"]:
            document.add_paragraph(bullet, style="List Bullet")
    document.add_heading("Education", level=1)
    document.add_paragraph("{} - {}, {}".format(*SENIOR["education"]))
    document.add_heading("Skills", level=1)
    document.add_paragraph(", ".join(SENIOR["skills"]))
    document.save(str(out / filename))


def _senior_pdf(out: Path, filename: str) -> None:
    def body(page: g.Page) -> None:
        page.line(SENIOR["name"], size=18, bold=True)
        page.line(SENIOR["contact"])
        page.line(SENIOR["location"])
        g.write_experience(page, SENIOR_JOBS)
        page.heading("Education")
        page.line("{} - {}, {}".format(*SENIOR["education"]))
        page.heading("Skills")
        page.line(", ".join(SENIOR["skills"]))

    g.pdf(out / filename, body)


def _fresher_pdf(out: Path, filename: str) -> None:
    def body(page: g.Page) -> None:
        page.line(FRESHER["name"], size=18, bold=True)
        page.line(FRESHER["contact"])
        page.heading("Education")
        page.line("{} - {}, {}".format(*FRESHER["education"]))
        page.heading("Skills")
        page.line(", ".join(FRESHER["skills"]))
        page.heading("Projects")
        page.line("{} - {}".format(*FRESHER["project"]))

    g.pdf(out / filename, body)


def _two_column_pdf(
    out: Path, filename: str, jobs: Sequence[dict[str, Any]], side: dict[str, Any]
) -> None:
    """Sidebar (contact, education, skills) on the left, experience on the right."""

    def body(page: g.Page) -> None:
        canvas = page.c
        top = page.y
        page.line(side["name"], size=18, bold=True)
        page.line(side["contact"], size=9)
        page.heading("Education")
        page.line(side["education"][0], size=9)
        page.line(side["education"][1], size=9)
        page.heading("Skills")
        for skill in side["skills"]:
            page.line(skill, size=9)
        page.y = top  # the right column starts at the same height
        for job in jobs:
            canvas.setFont("Helvetica-Bold", 10)
            canvas.drawString(260, page.y, f"{job['employer']} - {job['title']}")
            canvas.setFont("Helvetica", 9)
            canvas.drawString(260, page.y - 13, str(job["dates"]))
            page.y -= 30
            for bullet in job["bullets"]:
                canvas.drawString(270, page.y, f"- {str(bullet)[:48]}")
                page.y -= 14
            page.y -= 8

    g.pdf(out / filename, body)


def _rename(out: Path, old: str, new: str) -> None:
    (out / old).replace(out / new)


def build_cases(out: Path = CASES_DIR, expected_out: Path = EXPECTED_DIR) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    expected_out.mkdir(parents=True, exist_ok=True)
    mid_skills = list(g.SKILLS)
    mid_edu = [g.EDUCATION[0]]
    mid = _expected(g.JOBS, MID_DATES, name=g.NAME, skills=mid_skills, education=mid_edu)
    sen = _expected(
        SENIOR_JOBS,
        SENIOR_DATES,
        name=SENIOR["name"],
        skills=SENIOR["skills"],
        education=[SENIOR["education"][0]],
    )
    fre = _expected(
        [],
        {},
        name=FRESHER["name"],
        skills=FRESHER["skills"],
        education=[FRESHER["education"][0]],
    )
    tables = {**mid, "skills": [*mid_skills, "Kafka", "Docker", "Git"]}
    boxes = {**mid, "skills": [*mid_skills, "Kafka", "Rust", "gRPC"]}
    headers = _expected(
        g.JOBS[:1], MID_DATES, name=g.NAME, skills=["Python", "Go", "PostgreSQL"], education=[]
    )
    mid_side = {
        "name": g.NAME,
        "contact": g.CONTACT,
        "education": (g.EDUCATION[0], g.EDUCATION[1]),
        "skills": mid_skills,
    }
    cases: dict[str, dict[str, Any]] = {}

    g.pdf(out / "mid-single-column.pdf", g.standard_body())
    cases["mid-single-column.pdf"] = mid
    g.docx_resume(out / "mid-single-column.docx")
    cases["mid-single-column.docx"] = mid
    _senior_pdf(out, "senior-single-column.pdf")
    cases["senior-single-column.pdf"] = sen
    _senior_docx(out, "senior-single-column.docx")
    cases["senior-single-column.docx"] = sen
    g.build_fresher(out)
    _rename(out, "synthetic-fresher.docx", "fresher.docx")
    cases["fresher.docx"] = fre
    _fresher_pdf(out, "fresher.pdf")
    cases["fresher.pdf"] = fre
    _two_column_pdf(out, "mid-two-column.pdf", g.JOBS, mid_side)
    cases["mid-two-column.pdf"] = mid
    _two_column_pdf(out, "senior-two-column.pdf", SENIOR_JOBS, SENIOR)
    cases["senior-two-column.pdf"] = sen
    g.build_tables(out)
    _rename(out, "synthetic-tables.docx", "tables.docx")
    cases["tables.docx"] = tables
    g.build_textboxes(out)
    _rename(out, "synthetic-textboxes.docx", "textboxes.docx")
    cases["textboxes.docx"] = boxes
    g.build_headers_footers(out)
    _rename(out, "synthetic-headers-footers.docx", "headers-footers.docx")
    cases["headers-footers.docx"] = headers

    g.build_relieving_letter(out)
    _rename(out, "synthetic-relieving-letter.pdf", "relieving-letter.pdf")
    cases["relieving-letter.pdf"] = NOT_A_RESUME
    _offer_letter_docx(out, "offer-letter.docx")
    cases["offer-letter.docx"] = NOT_A_RESUME
    _certificate_pdf(out, "certificate.pdf")
    cases["certificate.pdf"] = NOT_A_RESUME
    _job_description_pdf(out, "job-description.pdf")
    cases["job-description.pdf"] = NOT_A_RESUME

    for filename, expected in cases.items():
        (expected_out / f"{filename}.yaml").write_text(
            yaml.safe_dump(expected, sort_keys=True, allow_unicode=True), encoding="utf-8"
        )
    return sorted(cases)


if __name__ == "__main__":
    names = build_cases()
    print(f"wrote {len(names)} eval cases to {CASES_DIR}")
