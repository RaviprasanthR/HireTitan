"""T043: what the AI says about an alert email is checked against the email (FR-013a).

The AI names a job's link by its number in the list it was shown and may only give a title,
company and place; every value must be words the email itself contains. Nothing is invented.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hiretitan.mail.domain.alert_checks import JOBS_MAX, Proposed, accept
from hiretitan.mail.domain.mime import Flat, Line, Link

DATE = datetime(2026, 11, 17, 8, tzinfo=UTC)


def email() -> Flat:
    return Flat(
        source="html",
        lines=[
            Line("Jobs for you this week"),
            Line("Data  Engineer"),  # two spaces: the email's own layout
            Line("Granite Insurance Tech · Gurugram"),
            Line("Site Reliability Engineer"),
            Line("Cobalt Mobility"),
        ],
        links=[
            Link("View job", "https://digest.example/jobs/aaa111?utm=x", 1),
            Link("View job", "https://digest.example/jobs/bbb222", 3),
            Link("Unsubscribe", "https://digest.example/unsubscribe", 4),
        ],
    )


def proposed(
    title: str = "Data Engineer",
    company: str | None = "Granite Insurance Tech",
    location: str | None = "Gurugram",
    link_index: int = 1,
) -> Proposed:
    return Proposed(title, company, location, link_index)


def run(*jobs: Proposed, site: str = "other") -> list:  # type: ignore[type-arg]
    return accept(jobs, email(), site=site, alert_date=DATE, shown=3)


def test_FR013a_link_by_index_only() -> None:
    (job,) = run(
        proposed(
            link_index=2,
            title="Site Reliability Engineer",
            company="Cobalt Mobility",
            location=None,
        )
    )

    assert job.link == "https://digest.example/jobs/bbb222"  # the email's own link, as given
    assert (job.site, job.alert_date) == ("other", DATE)


def test_FR013a_link_given_as_the_email_gave_it_not_rewritten() -> None:
    (job,) = run(proposed(link_index=1))

    assert job.link == "https://digest.example/jobs/aaa111?utm=x"


def test_FR013a_an_index_that_is_not_in_the_list_drops_the_job() -> None:
    assert run(proposed(link_index=0), proposed(link_index=4), proposed(link_index=99)) == []


def test_FR013a_an_index_beyond_what_was_shown_drops_the_job() -> None:
    # the list had 3 links but only 2 were shown to the AI: link 3 was never on offer
    out = accept([proposed(link_index=3)], email(), site="other", alert_date=DATE, shown=2)

    assert out == []


def test_FR013a_a_link_is_used_for_one_job_only() -> None:
    out = run(proposed(), proposed(title="Site Reliability Engineer", company=None, location=None))

    assert [j.title for j in out] == ["Data Engineer"]  # the first claim of a link wins


def test_FR013a_title_and_company_must_appear_in_email() -> None:
    assert run(proposed(title="Principal Rocket Scientist")) == []  # the title is not in the email
    (job,) = run(proposed(company="Globex Corporation", location="Mars"))

    assert job.title == "Data Engineer"
    assert (job.company, job.location) == (None, None)  # not in the email: left empty, not kept


def test_FR013a_words_match_whatever_the_case_and_spacing() -> None:
    (job,) = run(
        proposed(title="data engineer", company="GRANITE  insurance tech", location="gurugram")
    )

    # what is kept is the email's own writing, not the AI's
    assert (job.title, job.company, job.location) == (
        "Data Engineer",
        "Granite Insurance Tech",
        "Gurugram",
    )


def test_FR013a_a_value_must_be_whole_words_of_the_email() -> None:
    (job,) = run(proposed(company="Granite Insurance", location="Guru"))

    assert job.company == "Granite Insurance"  # whole words, as written in the email
    assert job.location is None  # "Guru" is only the start of "Gurugram"


def test_FR013a_a_value_may_not_be_stitched_from_two_lines() -> None:
    # "Data Engineer" is on one line and "Cobalt Mobility" on another
    assert run(proposed(title="Data Engineer Cobalt Mobility")) == []
    (job,) = run(proposed(company="Cobalt Mobility Granite Insurance Tech"))
    assert job.company is None


def test_FR013a_a_title_of_a_letter_or_two_is_not_accepted() -> None:
    assert run(proposed(title="a")) == []
    assert run(proposed(title="Da")) == []


def test_FR013a_invented_value_dropped() -> None:
    (job,) = run(proposed(location="Gurugram, Haryana, India"))  # more than the email says

    assert job.location is None
    assert job.company == "Granite Insurance Tech"


def test_FR013a_a_link_that_is_not_a_web_address_drops_the_job() -> None:
    flat = Flat(
        source="html",
        lines=[Line("Data Engineer")],
        links=[Link("Apply", "javascript:alert(1)", 0), Link("Apply", "mailto:hr@x.example", 0)],
    )

    out = accept(
        [Proposed("Data Engineer", None, None, 1), Proposed("Data Engineer", None, None, 2)],
        flat,
        site="other",
        alert_date=DATE,
        shown=2,
    )

    assert out == []


def test_FR013a_at_most_30_jobs() -> None:
    lines = [Line(f"Role {n}") for n in range(40)]
    links = [Link("Apply", f"https://digest.example/jobs/{n}", n) for n in range(40)]
    flat = Flat(source="html", lines=lines, links=links)

    out = accept(
        [Proposed(f"Role {n}", None, None, n + 1) for n in range(40)],
        flat,
        site="other",
        alert_date=DATE,
        shown=40,
    )

    assert len(out) == JOBS_MAX == 30


def test_FR013a_posting_id_only_when_the_site_is_known() -> None:
    flat = Flat(
        source="html",
        lines=[Line("Data Engineer"), Line("Acme")],
        links=[Link("View", "https://www.linkedin.com/comm/jobs/view/3978721496/?trk=x", 0)],
    )

    (known,) = accept(
        [Proposed("Data Engineer", "Acme", None, 1)],
        flat,
        site="linkedin",
        alert_date=DATE,
        shown=1,
    )
    (unknown,) = accept(
        [Proposed("Data Engineer", "Acme", None, 1)],
        flat,
        site="other",
        alert_date=DATE,
        shown=1,
    )

    assert known.posting_id == "3978721496"
    assert unknown.posting_id is None


def test_SEC_a_built_in_sites_job_must_link_to_that_site() -> None:
    # a planted or spoofed alert "from LinkedIn" cannot add a job that links somewhere else
    flat = Flat(
        source="html",
        lines=[Line("Data Engineer"), Line("Acme")],
        links=[
            Link("View", "https://login-linkedin.example/jobs/view/3978721496", 0),
            Link("View", "https://www.linkedin.com.evil.example/jobs/1", 0),
            Link("View", "https://www.linkedin.com/comm/jobs/view/3978721496/", 0),
        ],
    )

    jobs = accept(
        [Proposed("Data Engineer", "Acme", None, i) for i in (1, 2, 3)],
        flat,
        site="linkedin",
        alert_date=DATE,
        shown=3,
    )

    assert [j.link for j in jobs] == ["https://www.linkedin.com/comm/jobs/view/3978721496/"]


def test_SEC_an_added_senders_job_may_link_anywhere_on_the_web() -> None:
    (job,) = run(proposed(), site="other")

    assert job.link.startswith("https://digest.example/")
