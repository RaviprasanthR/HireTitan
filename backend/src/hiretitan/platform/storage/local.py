"""Local volume adapter: ``<data_dir>/files/<sha256[:2]>/<sha256>``.

Writes go to a temp file and are moved into place, so a crash never leaves a
half-written blob under its final name. Hashes and sidecar suffixes are
validated, so no caller-supplied string can escape the storage directory.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path

_SHA256 = re.compile(r"[0-9a-f]{64}")
_SUFFIX = re.compile(r"[a-z0-9]+(\.[a-z0-9]+)*")


def _check_sha(sha256: str) -> str:
    if not _SHA256.fullmatch(sha256):
        raise ValueError("expected a lowercase sha256 hex digest")
    return sha256


def _check_suffix(suffix: str) -> str:
    if not _SUFFIX.fullmatch(suffix):
        raise ValueError(f"invalid sidecar suffix: {suffix!r}")
    return suffix


class LocalFileStorage:
    def __init__(self, data_dir: Path) -> None:
        self._root = Path(data_dir) / "files"

    def _blob(self, sha256: str) -> Path:
        _check_sha(sha256)
        return self._root / sha256[:2] / sha256

    def _sidecar(self, sha256: str, suffix: str) -> Path:
        return self._blob(sha256).with_name(f"{sha256}.{_check_suffix(suffix)}")

    @staticmethod
    def _write_atomic(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def put(self, data: bytes) -> str:
        sha256 = hashlib.sha256(data).hexdigest()
        path = self._blob(sha256)
        if not path.exists():
            self._write_atomic(path, data)
        return sha256

    def get(self, sha256: str) -> bytes:
        return self._blob(sha256).read_bytes()

    def exists(self, sha256: str) -> bool:
        return self._blob(sha256).is_file()

    def put_text(self, sha256: str, suffix: str, text: str) -> None:
        self._write_atomic(self._sidecar(sha256, suffix), text.encode("utf-8"))

    def get_text(self, sha256: str, suffix: str) -> str:
        return self._sidecar(sha256, suffix).read_text(encoding="utf-8")

    def delete(self, sha256: str) -> None:
        blob = self._blob(sha256)
        if not blob.parent.is_dir():
            return
        for path in blob.parent.glob(f"{sha256}*"):
            if path.name == sha256 or path.name.startswith(f"{sha256}."):
                path.unlink(missing_ok=True)

    def delete_all(self) -> None:
        if self._root.exists():
            shutil.rmtree(self._root)
