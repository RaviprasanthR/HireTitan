"""T040: reading the text of a DOCX in document order (FR-004)."""

from __future__ import annotations

from pathlib import Path

from hiretitan.profile.infra.parsing.docx import parse_docx

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "resumes"


def parse(name: str):  # type: ignore[no-untyped-def]
    return parse_docx((FIXTURES / name).read_bytes())


def test_paragraphs_come_in_document_order_with_bullets() -> None:
    doc = parse("synthetic-mid-2page-v2.docx")
    lines = doc.visible_text.splitlines()

    assert lines[0] == "Jane Example"
    assert lines.index("Experience") < lines.index("Education") < lines.index("Skills")
    assert "• Led a team of 5 engineers on the billing platform migration" in lines
    assert any(line.startswith("Acme Corp - Staff Software Engineer") for line in lines)
    assert doc.status == "parsed"
    assert doc.hidden_runs == []
    assert doc.page_count is None


def test_FR004_tables_included() -> None:
    doc = parse("synthetic-tables.docx")
    lines = doc.visible_text.splitlines()
    assert "Languages | Python, Go, C++" in lines
    assert "Data | PostgreSQL, Kafka" in lines
    assert "Tools | Docker, Git" in lines
    assert lines.index("Technical skills") < lines.index("Languages | Python, Go, C++")


def test_FR004_text_boxes_included() -> None:
    doc = parse("synthetic-textboxes.docx")
    assert doc.visible_text.splitlines().count("Side panel: Kafka, Rust, gRPC") == 1


def test_FR004_headers_footers_included() -> None:
    doc = parse("synthetic-headers-footers.docx")
    lines = doc.visible_text.splitlines()
    assert "Jane Example | jane.example@example.com" in lines
    assert "Page footer: Pune, India | References on request" in lines
    assert lines[0].startswith("Jane Example")  # header first
    assert lines[-1].startswith("Page footer")  # footer last
    assert "Skills: Python, Go, PostgreSQL" in lines


def test_short_document_is_no_text_below_200_characters() -> None:
    doc = parse("synthetic-headers-footers.docx")
    assert len(doc.visible_text) < 200
    assert doc.status == "no_text"


def test_attack_text_is_kept_as_text_for_screening() -> None:
    doc = parse("attack-role-tags.docx")
    assert "<|im_start|>system" in doc.visible_text


def test_a_normal_docx_resume_has_enough_text() -> None:
    assert parse("synthetic-fresher.docx").visible_text.startswith("Sam Sample")
