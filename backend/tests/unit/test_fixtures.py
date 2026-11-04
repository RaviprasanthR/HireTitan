"""T033: the synthetic resume fixtures are fake, complete and reproducible (constitution VIII)."""

from __future__ import annotations

import hashlib
import re
import sys
import zipfile
from pathlib import Path

import pdfplumber
import pytest
import yaml

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "resumes"
sys.path.insert(0, str(FIXTURES))
from generate import FILES, build_all  # noqa: E402

RESERVED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}
EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
PHONE = re.compile(r"\+\d[\d ]{8,}\d")


def fingerprint(path: Path) -> str:
    """Content hash; DOCX is a zip with timestamps, so hash its members instead."""
    if path.suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            parts = b"".join(archive.read(name) for name in sorted(archive.namelist()))
        return hashlib.sha256(parts).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def all_text(path: Path) -> str:
    if path.suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            return "\n".join(
                archive.read(n).decode("utf-8", "ignore")
                for n in archive.namelist()
                if n.endswith(".xml")
            )
    if path.stem == "synthetic-encrypted":
        return ""
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_every_listed_fixture_is_committed_with_expected_facts() -> None:
    assert len(FILES) == 16
    for name in FILES:
        assert (FIXTURES / name).is_file(), name
    expected = sorted((FIXTURES / "expected").glob("*.yaml"))
    assert expected, "expected/*.yaml with the true facts"
    for path in expected:
        facts = yaml.safe_load(path.read_text("utf-8"))
        assert facts["name"]
        assert isinstance(facts["skills"], list)


@pytest.mark.parametrize("name", FILES)
def test_constitution_VIII_fixtures_synthetic(name: str) -> None:
    text = all_text(FIXTURES / name)
    for match in EMAIL.finditer(text):
        assert match.group(1).lower() in RESERVED_EMAIL_DOMAINS, match.group(0)
    for match in PHONE.finditer(text):
        assert match.group(0).replace(" ", "").startswith("+9190000"), match.group(0)


def test_generator_is_deterministic(tmp_path: Path) -> None:
    build_all(tmp_path / "a")
    build_all(tmp_path / "b")
    for name in FILES:
        assert fingerprint(tmp_path / "a" / name) == fingerprint(tmp_path / "b" / name), name


def test_committed_fixtures_match_the_generator(tmp_path: Path) -> None:
    build_all(tmp_path)
    for name in FILES:
        assert fingerprint(tmp_path / name) == fingerprint(FIXTURES / name), (
            f"{name} is stale: run `uv run python tests/fixtures/resumes/generate.py`"
        )


def test_special_fixtures_have_the_property_their_name_promises() -> None:
    with pdfplumber.open(FIXTURES / "synthetic-mid-2page.pdf") as pdf:
        assert len(pdf.pages) == 2
    with pdfplumber.open(FIXTURES / "synthetic-scanned.pdf") as pdf:
        assert not "".join(p.extract_text() or "" for p in pdf.pages).strip()
    assert len(all_text(FIXTURES / "synthetic-long.pdf")) > 30_000
    from pypdf import PdfReader

    assert PdfReader(FIXTURES / "synthetic-encrypted.pdf").is_encrypted
