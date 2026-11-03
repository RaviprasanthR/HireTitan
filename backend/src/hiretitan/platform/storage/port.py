"""FileStoragePort: content-addressed blobs plus text sidecars (``<sha>.<suffix>``)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class FileStoragePort(Protocol):
    def put(self, data: bytes) -> str:
        """Store ``data`` unchanged; return its sha256 hex. Same content is stored once."""
        ...

    def get(self, sha256: str) -> bytes: ...

    def exists(self, sha256: str) -> bool: ...

    def put_text(self, sha256: str, suffix: str, text: str) -> None:
        """Store a UTF-8 text sidecar (e.g. extracted text) next to a blob."""
        ...

    def get_text(self, sha256: str, suffix: str) -> str: ...

    def delete(self, sha256: str) -> None:
        """Delete a blob and all its sidecars. Missing files are ignored."""
        ...

    def delete_all(self) -> None:
        """Delete every stored blob and sidecar (FR-035)."""
        ...
