"""The OpenAI key saved from Settings (feature 002c US6, FR-029, FR-030; amends ADR-09).

``<data_dir>/secrets/llm.json`` holds ``{"openai_api_key": "..."}``, written atomically and
owner-only where the file system allows it. A key in the environment (``OPENAI_API_KEY``) wins
and cannot be changed from the page. The API saves the key and the worker reads it: ``current()``
reads the file again whenever it changes, so a new key takes effect without a restart.

The key is never returned by an API, never shown and never logged: every key read or saved here is
taught to the redacting log handler, and nothing in this class prints it.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Final, Literal

from pydantic import SecretStr

from hiretitan.platform.security.logging import register_secret

KeySource = Literal["env", "page", "none"]
FIELD: Final = "openai_api_key"
_SHAPE: Final = re.compile(r"[\x21-\x7e]{20,300}")  # printable, no spaces, 20 to 300 characters


def key_store_for(data_dir: Path, env_key: SecretStr | None) -> KeyStore:
    """The install's key store: ``<data_dir>/secrets/llm.json``, the environment winning."""
    return KeyStore(data_dir / "secrets" / "llm.json", env_key)


class KeyStoreError(ValueError):
    """The key cannot be saved or removed here (wrong shape, or it comes from the environment)."""


class KeyStore:
    def __init__(self, path: Path, env_key: SecretStr | None) -> None:
        self._path = path
        self._env = env_key.get_secret_value().strip() if env_key else ""
        self._lock = threading.Lock()
        self._seen: tuple[int, int, int] | None = None  # (mtime ns, size, inode) last read
        self._cached: str | None = None

    def __repr__(self) -> str:
        return f"KeyStore({self._path.name!r}, source={self.current()[1]!r})"

    __str__ = __repr__

    @property
    def from_environment(self) -> bool:
        return bool(self._env)

    def current(self) -> tuple[str | None, KeySource]:
        """The key to use and where it comes from."""
        if self._env:
            return self._env, "env"
        key = self._read()
        return (key, "page") if key else (None, "none")

    def has_key(self) -> bool:
        return self.current()[0] is not None

    def save(self, key: str) -> None:
        if self._env:
            raise KeyStoreError("The key comes from OPENAI_API_KEY in .env; change it there.")
        clean = key.strip()
        if not _SHAPE.fullmatch(clean):
            raise KeyStoreError("A key is 20 to 300 characters with no spaces.")
        register_secret(clean)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=self._path.parent, prefix=".llm-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump({FIELD: clean}, stream)
                if os.name != "nt":
                    os.chmod(temp, 0o600)
                os.replace(temp, self._path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(temp)
                raise
            self._seen = None

    def remove(self) -> None:
        if self._env:
            raise KeyStoreError("The key comes from OPENAI_API_KEY in .env; remove it there.")
        with self._lock:
            with contextlib.suppress(FileNotFoundError):
                self._path.unlink()
            self._seen = None

    def forget(self) -> None:
        """Delete all my data: remove a key saved on the page; a key in ``.env`` stays there."""
        if not self._env:
            self.remove()

    def _read(self) -> str | None:
        with self._lock:
            try:
                stat = self._path.stat()
            except FileNotFoundError:
                self._seen, self._cached = None, None
                return None
            # a replaced file has a new inode (os.replace), so the same size and a coarse clock on
            # a mounted folder cannot hide a new key
            mark = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            if mark == self._seen:
                return self._cached
            try:
                data = json.loads(self._path.read_text("utf-8"))
                value = data.get(FIELD) if isinstance(data, dict) else None
            except (OSError, ValueError):
                value = None  # a damaged file is no key: the page says "missing", nothing breaks
            key = (
                value.strip()
                if isinstance(value, str) and _SHAPE.fullmatch(value.strip())
                else None
            )
            if key:
                register_secret(key)
            self._seen, self._cached = mark, key
            return key
