"""The Google client id and secret and the refresh token, in one private file (research R7).

``<data_dir>/secrets/gmail.json``, written atomically and readable by the owner only where the
file system allows it. The client id and secret may instead come from the environment, which then
wins. Access tokens are never stored. Nothing here is logged, returned by an API or sent to an AI.

Every change is a locked read-modify-write, so a Disconnect and a late token save (the API and the
worker are two processes) cannot undo each other. A file that cannot be read is an error, never an
empty file: treating it as empty would let the next save drop the other values.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Final

from hiretitan.mail.application.ports import (
    CredentialsFromEnvironmentError,
    GoogleSecrets,
    SecretsFileError,
)
from hiretitan.platform.security.logging import register_secret

__all__ = ["CredentialsFromEnvironmentError", "GoogleSecrets", "SecretsFile", "SecretsFileError"]

ENV_CLIENT_ID: Final = "GOOGLE_OAUTH_CLIENT_ID"
ENV_CLIENT_SECRET: Final = "GOOGLE_OAUTH_CLIENT_SECRET"  # noqa: S105  (a variable name)
LOCK_WAIT_SECONDS: Final = 5.0
LOCK_STALE_SECONDS: Final = 15.0

_log = logging.getLogger(__name__)
_WARNED: set[str] = set()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock(path: Path) -> threading.RLock:
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(str(path), threading.RLock())


class SecretsFile:
    def __init__(self, path: Path, environ: Mapping[str, str]) -> None:
        self._path = path
        self._environ = environ

    def __repr__(self) -> str:
        return f"SecretsFile({self._path.name!r})"

    @property
    def credentials_from_environment(self) -> bool:
        return bool(self._environ.get(ENV_CLIENT_ID, "").strip()) and bool(
            self._environ.get(ENV_CLIENT_SECRET, "").strip()
        )

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        """One writer at a time, across threads and across processes (a lock file next to it)."""
        lock_path = self._path.with_name(self._path.name + ".lock")
        with _thread_lock(self._path):
            self._path.parent.mkdir(parents=True, exist_ok=True)
            owner = uuid.uuid4().hex  # written into the lock so only its owner removes it
            deadline = time.monotonic() + LOCK_WAIT_SECONDS
            while True:
                try:
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError:
                    self._take_over_if_stale(lock_path)
                    if time.monotonic() > deadline:
                        raise SecretsFileError("The Google secrets file is busy.") from None
                    time.sleep(0.01)
                    continue
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(owner)
                break
            try:
                yield
            finally:
                with contextlib.suppress(OSError):
                    if lock_path.read_text("utf-8") == owner:  # not one another process took over
                        lock_path.unlink()

    @staticmethod
    def _take_over_if_stale(lock_path: Path) -> None:
        """Clear a lock left by a process that died. The lock is moved aside with one atomic
        rename, so of several waiters only one succeeds and nobody deletes a fresh lock."""
        try:
            if time.time() - lock_path.stat().st_mtime <= LOCK_STALE_SECONDS:
                return
            aside = lock_path.with_name(f"{lock_path.name}.stale-{uuid.uuid4().hex}")
            os.replace(lock_path, aside)
        except OSError:
            return  # someone else got there first, or it is gone
        with contextlib.suppress(OSError):
            aside.unlink()

    def _check_private(self) -> None:
        if os.name == "nt":
            # Windows has no owner-only bits to check; say so once, never with a value in it
            key = str(self._path)
            if key not in _WARNED:
                _WARNED.add(key)
                _log.warning(
                    "The Google secrets file is protected by your Windows account's folder "
                    "permissions; it is not made owner-only."
                )
            return
        if self._path.stat().st_mode & 0o077:
            raise SecretsFileError(
                "The Google secrets file can be read by other users; run chmod 600 on it."
            )

    def _load(self) -> dict[str, Any]:
        try:
            raw = self._path.read_text("utf-8")
        except FileNotFoundError:
            return {}
        except OSError as error:
            raise SecretsFileError("The Google secrets file cannot be read.") from error
        self._check_private()
        try:
            data = json.loads(raw)
        except ValueError as error:
            raise SecretsFileError("The Google secrets file is damaged.") from error
        if not isinstance(data, dict):
            raise SecretsFileError("The Google secrets file is damaged.")
        return data

    def read(self) -> GoogleSecrets:
        data = self._load()
        client_id = _text(data.get("client_id"))
        client_secret = _text(data.get("client_secret"))
        if self.credentials_from_environment:
            client_id = self._environ[ENV_CLIENT_ID].strip()
            client_secret = self._environ[ENV_CLIENT_SECRET].strip()
        refresh = _text(data.get("refresh_token"))
        register_secret(client_secret, refresh)  # whoever reads them keeps them out of its logs
        return GoogleSecrets(client_id, client_secret, refresh)

    def save_credentials(self, client_id: str, client_secret: str) -> None:
        if self.credentials_from_environment:
            raise CredentialsFromEnvironmentError(
                "The Google client id and secret are set in the environment."
            )
        client_id, client_secret = client_id.strip(), client_secret.strip()
        register_secret(client_secret)
        with self._locked():
            data = self._load()
            if _text(data.get("client_id")) != client_id:
                data.pop("refresh_token", None)  # a token belongs to the client that issued it
            data.update(client_id=client_id, client_secret=client_secret)
            self._write(data)

    def save_refresh_token(self, token: str) -> None:
        register_secret(token)
        with self._locked():
            data = self._load()
            data["refresh_token"] = token
            self._write(data)

    def clear_token(self) -> None:
        with self._locked():
            data = self._load()
            data.pop("refresh_token", None)
            self._write(data)

    def clear_all(self) -> None:
        with self._locked(), contextlib.suppress(FileNotFoundError):
            self._path.unlink()

    def _write(self, data: dict[str, Any]) -> None:
        directory = self._path.parent
        directory.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            directory.chmod(0o700)
        handle, temp_name = tempfile.mkstemp(dir=directory, prefix=".gmail-", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
                stream.flush()
                os.fsync(stream.fileno())
            with contextlib.suppress(OSError):
                Path(temp_name).chmod(0o600)
            for attempt in range(5):
                try:
                    os.replace(temp_name, self._path)
                    break
                except PermissionError as error:  # Windows: another process has the file open
                    if attempt == 4:
                        raise SecretsFileError("The Google secrets file is busy.") from error
                    time.sleep(0.05)
        except BaseException:
            with contextlib.suppress(OSError):
                Path(temp_name).unlink()
            raise


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
