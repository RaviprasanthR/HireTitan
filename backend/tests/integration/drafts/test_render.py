"""PDF and DOCX rendering (T025): FR-018, SC-006."""

from __future__ import annotations

import re
from io import BytesIO

import pdfplumber
import pytest
from docx import Document
from tests.fakes.drafts_env import synthetic_content

from hiretitan.drafts.domain.resume_doc import (
    ResumeDocument,
    document_blocks,
    document_text,
    plain_reorder,
)
from hiretitan.drafts.infra.render.docx import render_docx
from hiretitan.drafts.infra.render.pdf import render_pdf
from hiretitan.drafts_wiring import profile_view


def words(lines: list[str]) -> list[str]:
    return re.findall(r"\S+", " ".join(lines))


def make(name: str = "Sam Rivera", extra_bullets: int = 0) -> ResumeDocument:
    doc = plain_reorder(profile_view(synthetic_content()), ["Python", "PostgreSQL"])
    doc = doc.model_copy(update={"contact": doc.contact.model_copy(update={"name": name})})
    if extra_bullets:
        doc.experience[0].bullets.extend(
            f"Extra bullet number {i} about Python & PostgreSQL <b>" for i in range(extra_bullets)
        )
    return doc


NAMES = ["Sam Rivera", "José Müller", "Zoë Çelik-O'Brien", "Ana & Co <Test>", "Noël Ångström"]


@pytest.mark.parametrize("name", NAMES)
def test_FR018_pdf_docx_same_text_single_column(name: str) -> None:
    doc = make(name, extra_bullets=3)
    expected = words(document_text(doc))

    with pdfplumber.open(BytesIO(render_pdf(doc))) as pdf:
        pdf_words = words([page.extract_text() or "" for page in pdf.pages])
    docx_words = words([p.text for p in Document(BytesIO(render_docx(doc))).paragraphs])

    assert docx_words == expected
    assert [w for w in pdf_words if w != "-"] == [w for w in expected if w != "-"]


def test_FR018_no_tables_or_images() -> None:
    doc = make(extra_bullets=40)  # long enough for a second page

    document = Document(BytesIO(render_docx(doc)))
    assert document.tables == []
    assert len(document.inline_shapes) == 0
    with pdfplumber.open(BytesIO(render_pdf(doc))) as pdf:
        assert len(pdf.pages) >= 2
        for page in pdf.pages:
            assert page.images == []
            assert page.find_tables() == []


def test_SC006_sections_in_order() -> None:
    doc = make()
    headings = [b.text for b in document_blocks(doc) if b.kind == "heading"]
    assert headings == [
        "Summary",
        "Experience",
        "Skills",
        "Projects",
        "Education",
        "Certifications",
    ]

    document = Document(BytesIO(render_docx(doc)))
    in_docx = [
        p.text for p in document.paragraphs if p.style is not None and p.style.name == "Heading 1"
    ]
    assert in_docx == headings
    with pdfplumber.open(BytesIO(render_pdf(doc))) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    positions = [text.index(h) for h in headings]
    assert positions == sorted(positions)
