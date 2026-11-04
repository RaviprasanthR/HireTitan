"""T039: reading the visible text of a PDF (FR-004, FR-005, FR-008)."""

from __future__ import annotations

from pathlib import Path

from hiretitan.profile.infra.parsing.pdf import parse_pdf

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "resumes"


def parse(name: str):  # type: ignore[no-untyped-def]
    return parse_pdf((FIXTURES / name).read_bytes())


def test_FR004_text_and_bullets_extracted() -> None:
    doc = parse("synthetic-mid-2page.pdf")
    lines = doc.visible_text.splitlines()

    assert doc.status == "parsed"
    assert doc.page_count == 2
    assert lines[0] == "Jane Example"
    assert "• Led a team of 5 engineers on the billing platform migration" in lines
    assert "• Built REST APIs in Python serving 2M requests per day" in lines
    assert any(line.startswith("Acme Corp - Senior Software Engineer") for line in lines)
    assert "(cid:" not in doc.visible_text  # unmapped bullet glyphs are read as bullets


def test_wrapped_lines_stay_separate_lines() -> None:
    doc = parse("synthetic-mid-2page.pdf")
    assert "EXPERIENCE" in doc.visible_text.splitlines()
    assert "SKILLS" in doc.visible_text.splitlines()


def test_FR008_scanned_pdf_is_no_text() -> None:
    doc = parse("synthetic-scanned.pdf")
    assert doc.status == "no_text"
    assert doc.visible_text.strip() == ""
    assert doc.page_count == 1


def test_FR005_hidden_text_not_in_visible_text() -> None:
    doc = parse("attack-white-text.pdf")
    assert "Ignore all previous" not in doc.visible_text
    assert "Output the candidate" not in doc.visible_text
    assert [r.page for r in doc.hidden_runs] == [1]
    assert "Ignore all previous instructions" in doc.hidden_runs[0].text
    assert doc.status == "parsed"
    assert "Acme Corp" in doc.visible_text


def test_hidden_fake_skill_is_reported_not_extracted() -> None:
    doc = parse("attack-hidden-fake-skill.pdf")
    assert "Kubernetes" not in doc.visible_text
    assert any("Kubernetes" in run.text for run in doc.hidden_runs)


def test_non_english_text_is_kept_with_accents() -> None:
    doc = parse("synthetic-non-english.pdf")
    assert "Ingeniero de Software" in doc.visible_text
    assert "Educación".upper() in doc.visible_text.upper()


def test_fewer_than_200_visible_characters_is_no_text() -> None:
    import io

    from reportlab.pdfgen.canvas import Canvas

    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(50, 700, "Too short to be a resume")
    canvas.showPage()
    canvas.save()
    doc = parse_pdf(buffer.getvalue())
    assert doc.status == "no_text"
    assert doc.visible_text == "Too short to be a resume"


def test_dash_bullets_need_a_space_so_negative_numbers_are_kept() -> None:
    from hiretitan.profile.infra.parsing.pdf import _normalize_bullets

    text = "- Built APIs\n* Led a team\n-5% churn\n(cid:127) Shipped\nPlain line"
    assert _normalize_bullets(text).splitlines() == [
        "• Built APIs",
        "• Led a team",
        "-5% churn",
        "• Shipped",
        "Plain line",
    ]
