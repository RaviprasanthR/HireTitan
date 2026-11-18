"""Render a tailored resume as an ATS-friendly PDF (research R8, spec FR-018).

One column, built-in Helvetica, standard section headings, no tables, images, text boxes, headers
or footers, so an applicant tracking system reads it in order. It draws exactly the blocks of
``document_blocks``, so the PDF and the DOCX say the same thing.
"""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from hiretitan.drafts.domain.resume_doc import ResumeDocument, document_blocks


def render_pdf(doc: ResumeDocument) -> bytes:
    base = getSampleStyleSheet()["Normal"]
    normal = ParagraphStyle("body", parent=base, fontName="Helvetica", fontSize=10, leading=13)
    styles = {
        "name": ParagraphStyle(
            "name", parent=normal, fontName="Helvetica-Bold", fontSize=18, leading=22
        ),
        "heading": ParagraphStyle(
            "heading",
            parent=normal,
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            spaceBefore=10,
            spaceAfter=3,
        ),
        "title": ParagraphStyle(
            "title", parent=normal, fontName="Helvetica-Bold", spaceBefore=4, leading=13
        ),
        "line": normal,
        "bullet": ParagraphStyle("bullet", parent=normal, leftIndent=12, bulletIndent=0),
    }
    story: list[Paragraph | Spacer] = []
    for block in document_blocks(doc):
        text = escape(block.text)
        if block.kind == "bullet":
            story.append(Paragraph(text, styles["bullet"], bulletText="-"))
        else:
            story.append(Paragraph(text, styles[block.kind]))
    out = BytesIO()
    SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"{doc.contact.name} resume",
        author=doc.contact.name,
    ).build(story)
    return out.getvalue()
