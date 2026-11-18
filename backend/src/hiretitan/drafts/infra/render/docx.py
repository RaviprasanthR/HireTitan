"""Render a tailored resume as an ATS-friendly DOCX (research R8, spec FR-018).

Built-in styles only, one column, no tables or images. It draws exactly the blocks of
``document_blocks``, so the DOCX and the PDF say the same thing.
"""

from __future__ import annotations

from io import BytesIO

from docx import Document
from docx.shared import Pt

from hiretitan.drafts.domain.resume_doc import ResumeDocument, document_blocks


def render_docx(doc: ResumeDocument) -> bytes:
    document = Document()
    document.core_properties.title = f"{doc.contact.name} resume"
    document.core_properties.author = doc.contact.name
    for block in document_blocks(doc):
        if block.kind == "name":
            paragraph = document.add_paragraph(style="Title")
            paragraph.add_run(block.text)
        elif block.kind == "heading":
            document.add_paragraph(block.text, style="Heading 1")
        elif block.kind == "bullet":
            document.add_paragraph(block.text, style="List Bullet")
        elif block.kind == "title":
            paragraph = document.add_paragraph()
            run = paragraph.add_run(block.text)
            run.bold = True
            run.font.size = Pt(11)
        else:
            document.add_paragraph(block.text)
    out = BytesIO()
    document.save(out)
    return out.getvalue()
