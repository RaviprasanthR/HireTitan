"""T038: what a file really is, and whether we accept it (FR-001), whatever its name says."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from hiretitan.profile.infra.parsing.sniff import (
    MAX_BYTES,
    CorruptFileError,
    EncryptedFileError,
    FileTooLargeError,
    PasswordProtectedOrLegacyDocError,
    TooManyPagesError,
    UnsupportedTypeError,
    read_limited,
    sniff,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "resumes"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def pdf_with_pages(count: int) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    for n in range(count):
        canvas.drawString(50, 700, f"page {n}")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def test_pdf_and_docx_are_recognised_by_content() -> None:
    pdf = sniff(fixture("synthetic-mid-2page.pdf"))
    assert (pdf.kind, pdf.page_count) == ("pdf", 2)
    docx = sniff(fixture("synthetic-fresher.docx"))
    assert (docx.kind, docx.page_count) == ("docx", None)


def test_scanned_pdf_is_accepted_at_intake() -> None:
    # "No readable text" is decided later, by the parser; intake only checks the file.
    assert sniff(fixture("synthetic-scanned.pdf")).kind == "pdf"


def test_FR001_rejects_renamed_exe_as_pdf() -> None:
    fake = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 200
    with pytest.raises(UnsupportedTypeError):
        sniff(fake)


@pytest.mark.parametrize("data", [b"", b"just plain text", b"\x89PNG\r\n\x1a\n", b"<html></html>"])
def test_other_types_are_unsupported(data: bytes) -> None:
    with pytest.raises(UnsupportedTypeError):
        sniff(data)


def test_a_zip_that_is_not_a_docx_is_unsupported() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "hello")
    with pytest.raises(UnsupportedTypeError):
        sniff(buffer.getvalue())


def test_FR001_rejects_encrypted_pdf() -> None:
    with pytest.raises(EncryptedFileError):
        sniff(fixture("synthetic-encrypted.pdf"))


def test_FR001_rejects_corrupt_docx() -> None:
    with pytest.raises(CorruptFileError):
        sniff(b"PK\x03\x04" + b"garbage" * 50)


def test_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(CorruptFileError):
        sniff(b"%PDF-1.7\nthis is not a real pdf body\n%%EOF")


def test_edge_case_password_protected_docx_specific_message() -> None:
    ole = bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 512
    with pytest.raises(PasswordProtectedOrLegacyDocError) as raised:
        sniff(ole)
    assert str(raised.value) == (
        "This looks like a password-protected or old .doc file. "
        "Remove the password or save it as .docx or PDF"
    )


def test_more_than_20_pages_is_rejected() -> None:
    assert sniff(pdf_with_pages(20)).page_count == 20
    with pytest.raises(TooManyPagesError):
        sniff(pdf_with_pages(21))


def chunks(total: int, size: int, consumed: list[int]) -> Iterator[bytes]:
    sent = 0
    while sent < total:
        piece = min(size, total - sent)
        sent += piece
        consumed.append(piece)
        yield b"x" * piece


def test_FR001_rejects_over_10mb() -> None:
    consumed: list[int] = []
    with pytest.raises(FileTooLargeError):
        read_limited(chunks(MAX_BYTES * 3, 1_000_000, consumed))
    # It stopped as soon as the limit was crossed instead of reading the whole upload.
    assert sum(consumed) <= MAX_BYTES + 1_000_000


def test_exactly_10mb_is_accepted() -> None:
    data = read_limited(chunks(MAX_BYTES, 1_048_576, []))
    assert len(data) == MAX_BYTES == 10_485_760


def test_empty_upload_is_unsupported() -> None:
    with pytest.raises(UnsupportedTypeError):
        sniff(read_limited(iter(())))
