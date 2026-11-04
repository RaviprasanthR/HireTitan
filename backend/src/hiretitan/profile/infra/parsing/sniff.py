"""File intake checks (FR-001, research R8): what a file really is, by its bytes.

The extension and the browser's content type are never trusted. Rejections carry a message
the user can act on; the API maps them to 415, 413 or 422.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Literal

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MAX_BYTES: Final = 5_242_880
MAX_PAGES: Final = 20
MAX_UNPACKED_BYTES: Final = 50 * 1024 * 1024  # a 5 MB DOCX never legitimately unpacks past this
MAX_ZIP_ENTRIES: Final = 1000
_OLE_MAGIC: Final = bytes.fromhex("D0CF11E0")
_ZIP_MAGIC: Final = b"PK\x03\x04"
_PDF_MAGIC: Final = b"%PDF-"


class IntakeError(Exception):
    """A file we will not accept; the message is shown to the user."""


class UnsupportedTypeError(IntakeError):  # -> 415
    def __init__(self) -> None:
        super().__init__("Only PDF and DOCX files are supported")


class PasswordProtectedOrLegacyDocError(IntakeError):  # -> 415
    def __init__(self) -> None:
        super().__init__(
            "This looks like a password-protected or old .doc file. "
            "Remove the password or save it as .docx or PDF"
        )


class FileTooLargeError(IntakeError):  # -> 413
    def __init__(self) -> None:
        super().__init__("The file is larger than 5 MB")


class UnpackedTooLargeError(IntakeError):  # -> 422
    def __init__(self) -> None:
        super().__init__("This file is far larger once unpacked than a resume should be")


class EncryptedFileError(IntakeError):  # -> 422
    def __init__(self) -> None:
        super().__init__("This PDF is password-protected. Remove the password and upload it again")


class CorruptFileError(IntakeError):  # -> 422
    def __init__(self) -> None:
        super().__init__("This file could not be read. It may be damaged")


class TooManyPagesError(IntakeError):  # -> 422
    def __init__(self) -> None:
        super().__init__(f"The PDF has more than {MAX_PAGES} pages")


@dataclass(frozen=True, slots=True)
class Sniffed:
    kind: Literal["pdf", "docx"]
    page_count: int | None  # PDF only


def read_limited(chunks: Iterable[bytes], limit: int = MAX_BYTES) -> bytes:
    """Collect an upload, failing as soon as it passes ``limit`` instead of after reading it."""
    parts: list[bytes] = []
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > limit:
            raise FileTooLargeError
        parts.append(chunk)
    return b"".join(parts)


def _sniff_pdf(data: bytes) -> Sniffed:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise EncryptedFileError
        pages = len(reader.pages)
    except IntakeError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError, RecursionError):
        raise CorruptFileError from None
    if pages > MAX_PAGES:
        raise TooManyPagesError
    return Sniffed("pdf", pages)


def _sniff_docx(data: bytes) -> Sniffed:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES:
                raise UnpackedTooLargeError
            names = {i.filename for i in infos}
            if "word/document.xml" not in names:
                raise UnsupportedTypeError
            if archive.testzip() is not None:
                raise CorruptFileError
    except IntakeError:
        raise
    except (zipfile.BadZipFile, OSError, ValueError, EOFError):
        raise CorruptFileError from None
    return Sniffed("docx", None)


def sniff(data: bytes) -> Sniffed:
    """Identify the file from its first bytes and check it can be read."""
    if data.startswith(_PDF_MAGIC):
        return _sniff_pdf(data)
    if data.startswith(_ZIP_MAGIC):
        return _sniff_docx(data)
    if data.startswith(_OLE_MAGIC):
        raise PasswordProtectedOrLegacyDocError
    raise UnsupportedTypeError
