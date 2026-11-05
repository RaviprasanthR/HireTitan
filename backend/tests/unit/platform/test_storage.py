"""T011: content-addressed local file storage (FR-003: the uploaded file is kept unchanged)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hiretitan.platform.storage import FileStoragePort, LocalFileStorage

PDF = b"%PDF-1.7\n synthetic resume bytes \x00\x01\x02"


@pytest.fixture
def storage(tmp_data_dir: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_data_dir)


def test_FR003_file_stored_unchanged_by_hash(storage: LocalFileStorage, tmp_data_dir: Path) -> None:
    sha = storage.put(PDF)

    assert sha == hashlib.sha256(PDF).hexdigest()
    path = tmp_data_dir / "files" / sha[:2] / sha
    assert path.read_bytes() == PDF
    assert storage.get(sha) == PDF
    assert storage.exists(sha)


def test_same_content_stored_once(storage: LocalFileStorage, tmp_data_dir: Path) -> None:
    assert storage.put(PDF) == storage.put(PDF)
    stored = [p for p in (tmp_data_dir / "files").rglob("*") if p.is_file()]
    assert len(stored) == 1


def test_put_text_sidecar_round_trips(storage: LocalFileStorage) -> None:
    sha = storage.put(PDF)
    storage.put_text(sha, "txt", "Extracted text — with ünïcode")
    assert storage.get_text(sha, "txt") == "Extracted text — with ünïcode"


def test_delete_removes_sidecars(storage: LocalFileStorage, tmp_data_dir: Path) -> None:
    sha = storage.put(PDF)
    other = storage.put(b"another file")
    storage.put_text(sha, "txt", "text")
    storage.put_text(sha, "masked.txt", "masked")

    storage.delete(sha)

    assert not storage.exists(sha)
    assert list((tmp_data_dir / "files" / sha[:2]).glob(f"{sha}*")) == []
    assert storage.exists(other)


def test_delete_missing_is_a_no_op(storage: LocalFileStorage) -> None:
    storage.delete("0" * 64)


def test_delete_all_empties_storage_only(storage: LocalFileStorage, tmp_data_dir: Path) -> None:
    keep = tmp_data_dir / "unrelated.txt"
    keep.write_text("not ours")
    storage.put(PDF)
    storage.put(b"two")

    storage.delete_all()

    assert not storage.exists(hashlib.sha256(PDF).hexdigest())
    assert keep.exists()
    assert storage.put(PDF)  # still usable afterwards


@pytest.mark.parametrize("bad", ["../../etc/passwd", "ABC", "g" * 64, "A" * 64, "0" * 63, ""])
def test_invalid_hash_rejected(storage: LocalFileStorage, bad: str) -> None:
    with pytest.raises(ValueError, match="sha256"):
        storage.get(bad)


@pytest.mark.parametrize("suffix", ["../x", "a/b", "", ".txt", "a\b"])
def test_invalid_sidecar_suffix_rejected(storage: LocalFileStorage, suffix: str) -> None:
    sha = storage.put(PDF)
    with pytest.raises(ValueError, match="suffix"):
        storage.put_text(sha, suffix, "x")


def test_get_missing_raises(storage: LocalFileStorage) -> None:
    with pytest.raises(FileNotFoundError):
        storage.get("0" * 64)


def test_local_storage_satisfies_port(storage: LocalFileStorage) -> None:
    assert isinstance(storage, FileStoragePort)
