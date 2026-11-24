"""The shape of an alert email, with every word masked (2026-11-22): what a reader needs to know
about a site's layout, without any job title, company, place or name in it."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from hiretitan.mail.domain.alerts import AlertJob
from hiretitan.mail.domain.mime import Flat, Line, Link
from hiretitan.mail.domain.skeleton import link_shape, mask, skeleton

DATE = datetime(2026, 11, 22, tzinfo=UTC)
WORDS = ["Backend", "Engineer", "Acme", "Robotics", "Pune", "Jane", "Example", "intended"]


def email() -> Flat:
    return Flat(
        source="html",
        lines=[
            Line("Your job alert for Backend Engineer"),
            Line("Backend Engineer"),
            Line("Acme Robotics · Pune"),
            Line("Be an early applicant", muted=True),
            Line("This email was intended for Jane Example"),
        ],
        links=[
            Link(
                "Backend Engineer",
                "https://www.linkedin.com/comm/jobs/view/4012345678/?trk=abc&ref=jane",
                1,
            ),
            Link("Unsubscribe", "https://tracking.example.invalid/u/jane-example?x=1", 4),
        ],
        hidden=["secret preheader text"],
    )


def found() -> list[AlertJob]:
    return [
        AlertJob(
            title="Backend Engineer",
            company="This email was intended for Jane Example",
            location=None,
            link="https://www.linkedin.com/comm/jobs/view/4012345678/?trk=abc&ref=jane",
            posting_id="4012345678",
            site="linkedin",
            alert_date=DATE,
        )
    ]


def test_letters_and_digits_are_masked_and_the_rest_is_kept() -> None:
    assert mask("Acme Robotics · Pune, 2 days ago!") == "Xxxx Xxxxxxxx · Xxxx, 9 xxxx xxx!"
    assert mask("") == ""


def test_a_job_site_link_keeps_its_host_and_the_shape_of_its_path() -> None:
    shape = link_shape("https://www.linkedin.com/comm/jobs/view/4012345678/?trk=abc&ref=jane")

    assert shape == "https://www.linkedin.com/xxxx/xxxx/xxxx/9999999999/ ?…"


def test_a_link_to_any_other_host_is_masked_whole() -> None:
    shape = link_shape("https://tracking.example.invalid/u/jane-example?x=1")

    assert shape == "https://xxxxxxxx.xxxxxxx.xxxxxxx/x/xxxx-xxxxxxx ?…"
    assert link_shape("mailto:jane@example.invalid") == "xxxxxx:xxxx@xxxxxxx.xxxxxxx"


def test_the_skeleton_shows_lines_links_and_what_the_reader_took() -> None:
    out = "\n".join(skeleton(email(), found()))

    assert "L01 Xxxxxxx Xxxxxxxx" in out
    assert "L03 (muted) Xx xx xxxxx xxxxxxxxx" in out
    assert "link 1 on L01" in out
    assert "https://www.linkedin.com/xxxx/xxxx/xxxx/9999999999/" in out
    assert "hidden text: 1 block" in out
    # the reader took the title from L01 and (wrongly) the company from L04: that is what the
    # skeleton is for
    assert "job 1: title=L01 company=L04 location=none link=1" in out


def test_no_word_of_the_email_is_in_the_skeleton() -> None:
    out = "\n".join(skeleton(email(), found())).casefold()

    for word in [*WORDS, "secret", "preheader", "trk", "jane-example", "unsubscribe"]:
        assert word.casefold() not in out, word


def test_a_value_the_reader_did_not_find_in_any_line_is_marked() -> None:
    other = replace(found()[0], company="Not In The Email")

    out = "\n".join(skeleton(email(), [other]))

    assert "company=?" in out
