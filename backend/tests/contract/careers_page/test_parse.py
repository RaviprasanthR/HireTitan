"""T052: reading job postings out of a careers page (research R3).

The pages are recorded text under ``pages/``; nothing here touches the network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hiretitan.search.infra.careers_page.parse import MAX_POSTINGS, parse_careers_page

PAGES = Path(__file__).parent / "pages"


def page(name: str) -> str:
    return (PAGES / name).read_text("utf-8")


def test_R3_json_ld_postings_parsed() -> None:
    result = parse_careers_page(page("jsonld.html"), "https://careers.northwind.example/")

    assert (result.status, result.via) == ("found", "json_ld")
    backend, analyst, sre = result.postings
    assert backend.title == "Backend Engineer"
    assert backend.url == "https://careers.northwind.example/jobs/backend-engineer"
    assert backend.location == "Pune, MH, IN"
    assert backend.posted_at == datetime(2026, 11, 2, tzinfo=UTC)
    assert backend.requisition_id == "REQ-1042"
    assert backend.description == "Build payment APIs in Python.\n3+ years"
    # a posting inside @graph, a remote one, and a date with an offset
    assert analyst.title == "Data Analyst"
    assert analyst.location == "Remote"
    assert analyst.posted_at is not None
    assert analyst.posted_at.utcoffset() is not None
    # "name" instead of "title", a list of types, and several places
    assert sre.title == "Site Reliability Engineer"
    assert sre.location == "Chennai, India; Pune, India"


def test_json_ld_that_is_not_valid_is_skipped_not_fatal() -> None:
    # the third script in jsonld.html is broken; the other two still gave three postings
    assert (
        len(parse_careers_page(page("jsonld.html"), "https://careers.northwind.example/").postings)
        == 3
    )


def test_R3_plain_list_links_parsed() -> None:
    result = parse_careers_page(page("plain_list.html"), "https://careers.example.com/careers")

    assert (result.status, result.via) == ("found", "links")
    assert [(p.title, p.url) for p in result.postings] == [
        ("Senior Python Developer", "https://careers.example.com/careers/senior-python-developer"),
        ("QA Engineer", "https://careers.example.com/careers/qa-engineer-manual"),
        ("UI Designer", "https://careers.example.com/openings/ui-designer"),
    ]
    # the link text is all that is known about a posting found this way
    assert all(p.location is None and p.description is None for p in result.postings)


def test_navigation_and_other_sites_are_not_jobs() -> None:
    titles = {
        p.title
        for p in parse_careers_page(
            page("plain_list.html"), "https://careers.example.com/careers"
        ).postings
    }

    assert titles.isdisjoint(
        {"Home", "About us", "Careers", "Contact", "Privacy", "View all jobs", "Back to top"}
    )
    assert not any("Twitter" in t or "heart" in t for t in titles)


def test_R3_js_only_page_is_unreadable() -> None:
    result = parse_careers_page(page("js_only.html"), "https://careers.example.com/")

    assert (result.status, result.postings, result.via) == ("unreadable", [], None)


def test_a_real_page_without_openings_is_empty_not_unreadable() -> None:
    result = parse_careers_page(page("no_openings.html"), "https://careers.example.com/")

    assert (result.status, result.postings) == ("empty", [])


def test_json_ld_wins_over_links() -> None:
    html = (
        '<script type="application/ld+json">{"@type":"JobPosting","title":"Analyst",'
        '"url":"https://x.example/jobs/analyst"}</script>'
        "<p>Open roles for people who like to build things and ship them with care, every week.</p>"
        '<a href="/jobs/qa-engineer">QA Engineer</a>'
    )

    result = parse_careers_page(html, "https://x.example/")

    assert result.via == "json_ld"
    assert [p.title for p in result.postings] == ["Analyst"]


def test_a_posting_without_a_title_is_skipped_and_one_without_a_link_uses_the_page() -> None:
    html = (
        '<script type="application/ld+json">[{"@type":"JobPosting"},'
        '{"@type":"JobPosting","title":"Analyst"}]</script>'
    )

    result = parse_careers_page(html, "https://x.example/careers")

    assert [(p.title, p.url) for p in result.postings] == [("Analyst", "https://x.example/careers")]


def test_the_same_posting_twice_is_listed_once() -> None:
    one = '{"@type":"JobPosting","title":"Analyst","url":"https://x.example/jobs/1"}'

    result = parse_careers_page(
        f'<script type="application/ld+json">[{one},{one}]</script>', "https://x.example/"
    )

    assert len(result.postings) == 1


def test_the_number_of_postings_is_capped() -> None:
    items = ",".join(
        f'{{"@type":"JobPosting","title":"Role {i}","url":"https://x.example/jobs/{i}"}}'
        for i in range(MAX_POSTINGS + 20)
    )

    result = parse_careers_page(
        f'<script type="application/ld+json">[{items}]</script>', "https://x.example/"
    )

    assert len(result.postings) == MAX_POSTINGS


def test_links_with_a_scheme_that_is_not_http_are_ignored() -> None:
    html = (
        "<p>We are hiring and would love to hear from you, so please look at the roles we have.</p>"
        '<a href="javascript:void(0)">Software Engineer</a>'
        '<a href="mailto:a@b.example">Software Engineer</a>'
        '<a href="/jobs/software-engineer">Software Engineer</a>'
    )

    result = parse_careers_page(html, "https://x.example/")

    assert [p.url for p in result.postings] == ["https://x.example/jobs/software-engineer"]


def test_garbage_input_does_not_raise() -> None:
    for text in ("", "<", "<<<>>>", "\x00\x01", "<a href=", "<script type='application/ld+json'>"):
        assert parse_careers_page(text, "https://x.example/").postings == []
