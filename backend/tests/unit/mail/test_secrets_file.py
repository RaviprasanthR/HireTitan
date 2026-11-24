"""The Google secrets file (T008): FR-003, research R7. Nothing here ever appears in a log."""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path

import pytest

from hiretitan.mail.infra.secrets_file import CredentialsFromEnvironmentError, SecretsFile
from hiretitan.platform.security.logging import REDACTED, JsonFormatter

CLIENT_ID = "1234567890-abcdefghij.apps.googleusercontent.invalid"
CLIENT_SECRET = "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"
REFRESH = "1//0g-synthetic-refresh-token-value-0002"
ACCESS = "ya29.synthetic-access-token-value-0003"


def make(tmp_path: Path, environ: dict[str, str] | None = None) -> SecretsFile:
    return SecretsFile(tmp_path / "secrets" / "gmail.json", environ or {})


def test_FR003_round_trip_and_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secrets = make(tmp_path)
    assert secrets.read().client_id is None

    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    secrets.save_refresh_token(REFRESH)

    read = secrets.read()
    assert (read.client_id, read.client_secret, read.refresh_token) == (
        CLIENT_ID,
        CLIENT_SECRET,
        REFRESH,
    )
    path = tmp_path / "secrets" / "gmail.json"
    assert json.loads(path.read_text("utf-8"))["refresh_token"] == REFRESH

    # a write that fails half way leaves the old file whole and no temporary file behind
    def broken(_src: object, _dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError):
        secrets.save_refresh_token("1//0g-another")
    monkeypatch.undo()
    assert secrets.read().refresh_token == REFRESH
    assert [p.name for p in (tmp_path / "secrets").iterdir()] == ["gmail.json"]


def test_FR003_the_file_is_private_where_the_system_allows_it(tmp_path: Path) -> None:
    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)

    if os.name == "posix":
        mode = (tmp_path / "secrets" / "gmail.json").stat().st_mode & 0o777
        assert mode == 0o600


def test_FR003_env_wins(tmp_path: Path) -> None:
    secrets = make(
        tmp_path,
        {"GOOGLE_OAUTH_CLIENT_ID": "env-id.invalid", "GOOGLE_OAUTH_CLIENT_SECRET": "env-secret-1"},
    )

    read = secrets.read()
    assert (read.client_id, read.client_secret) == ("env-id.invalid", "env-secret-1")
    assert secrets.credentials_from_environment is True
    with pytest.raises(CredentialsFromEnvironmentError):
        secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    secrets.save_refresh_token(REFRESH)  # the token is always the file's
    assert secrets.read().refresh_token == REFRESH


def test_FR003_half_an_environment_pair_is_ignored(tmp_path: Path) -> None:
    secrets = make(tmp_path, {"GOOGLE_OAUTH_CLIENT_ID": "env-id.invalid"})

    assert secrets.credentials_from_environment is False
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    assert secrets.read().client_id == CLIENT_ID


def test_FR004_clearing_the_token_keeps_the_credentials_and_clear_all_removes_the_file(
    tmp_path: Path,
) -> None:
    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    secrets.save_refresh_token(REFRESH)

    secrets.clear_token()
    read = secrets.read()
    assert (read.client_id, read.refresh_token) == (CLIENT_ID, None)

    secrets.clear_all()
    assert not (tmp_path / "secrets" / "gmail.json").exists()
    secrets.clear_all()  # nothing to remove is not an error


def test_FR003_never_in_repr_or_logs(tmp_path: Path) -> None:
    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    secrets.save_refresh_token(REFRESH)
    read = secrets.read()

    shown = repr(read) + str(read) + repr(secrets)
    for secret in (CLIENT_SECRET, REFRESH):
        assert secret not in shown

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("hiretitan.test.google")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.info("token exchange", extra={"client_secret": CLIENT_SECRET, "refresh_token": REFRESH})
    logger.info(f"Authorization: Bearer {ACCESS} and refresh {REFRESH} and {CLIENT_SECRET}")
    logger.info("nested", extra={"body": {"access_token": ACCESS, "id_token": "eyJ.synthetic.jwt"}})
    logger.handlers = []

    out = stream.getvalue()
    for secret in (CLIENT_SECRET, REFRESH, ACCESS, "eyJ.synthetic.jwt"):
        assert secret not in out
    assert REDACTED in out


def test_FR003_a_damaged_file_is_an_error_not_an_empty_file(tmp_path: Path) -> None:
    from hiretitan.mail.infra.secrets_file import SecretsFileError

    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    secrets.save_refresh_token(REFRESH)
    (tmp_path / "secrets" / "gmail.json").write_text("{not json", "utf-8")

    # reading "empty" here would let a save drop the other values, or a disconnect that raced it
    # bring a revoked token back; so a parse error stops the caller
    with pytest.raises(SecretsFileError):
        secrets.read()
    with pytest.raises(SecretsFileError):
        secrets.save_refresh_token("1//another")
    assert (tmp_path / "secrets" / "gmail.json").read_text("utf-8") == "{not json"


def test_FR003_a_missing_file_reads_as_empty(tmp_path: Path) -> None:
    assert make(tmp_path).read().refresh_token is None


def test_FR003_changing_the_client_id_drops_the_refresh_token(tmp_path: Path) -> None:
    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    secrets.save_refresh_token(REFRESH)

    secrets.save_credentials(CLIENT_ID, "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ient")  # same client
    assert secrets.read().refresh_token == REFRESH

    secrets.save_credentials("another-client.apps.googleusercontent.invalid", CLIENT_SECRET)
    assert secrets.read().refresh_token is None  # a token belongs to the client that got it


def test_FR003_concurrent_writers_do_not_lose_each_other(tmp_path: Path) -> None:
    import threading

    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            for i in range(10):
                secrets.save_refresh_token(f"1//token-{n}-{i}")
        except BaseException as error:
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    read = secrets.read()
    assert read.client_id == CLIENT_ID
    assert read.refresh_token is not None


def test_FR003_a_clear_then_a_late_save_cannot_bring_back_a_token(tmp_path: Path) -> None:
    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    secrets.save_refresh_token(REFRESH)

    secrets.clear_token()

    assert secrets.read().refresh_token is None
    assert secrets.read().client_id == CLIENT_ID


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_FR003_a_file_others_can_read_is_refused_on_posix(tmp_path: Path) -> None:
    from hiretitan.mail.infra.secrets_file import SecretsFileError

    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    (tmp_path / "secrets" / "gmail.json").chmod(0o644)

    with pytest.raises(SecretsFileError):
        secrets.read()


@pytest.mark.skipif(os.name != "nt", reason="the one-time Windows notice")
def test_FR003_windows_notes_once_that_the_file_is_not_owner_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from hiretitan.mail.infra import secrets_file

    secrets_file._WARNED.clear()
    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    with caplog.at_level(logging.WARNING):
        secrets.read()
        secrets.read()

    notes = [r for r in caplog.records if "owner" in r.getMessage()]
    assert len(notes) == 1
    assert CLIENT_SECRET not in caplog.text


def test_FR003_the_secret_values_are_registered_with_the_log_scrubber(tmp_path: Path) -> None:
    stream = io.StringIO()
    from hiretitan.platform.security.logging import configure_logging

    configure_logging([], stream=stream)
    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, "an-oddly-shaped-secret-without-prefix")
    secrets.save_refresh_token("an-oddly-shaped-refresh-token")

    logging.getLogger("hiretitan.test.mail").info(
        "oops an-oddly-shaped-secret-without-prefix an-oddly-shaped-refresh-token %s", CLIENT_ID
    )

    out = stream.getvalue()
    assert "an-oddly-shaped-secret-without-prefix" not in out
    assert "an-oddly-shaped-refresh-token" not in out


def _lock_path(tmp_path: Path) -> Path:
    return tmp_path / "secrets" / "gmail.json.lock"


def test_FR003_a_busy_lock_times_out_and_is_not_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hiretitan.mail.application.ports import SecretsFileError
    from hiretitan.mail.infra import secrets_file

    monkeypatch.setattr(secrets_file, "LOCK_WAIT_SECONDS", 0.05)
    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    _lock_path(tmp_path).write_text("someone-else", "utf-8")  # a live holder, just now

    with pytest.raises(SecretsFileError):
        secrets.save_refresh_token(REFRESH)

    assert _lock_path(tmp_path).read_text("utf-8") == "someone-else"  # never stolen


def test_FR003_a_stale_lock_is_taken_over(tmp_path: Path) -> None:
    import time

    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)
    lock = _lock_path(tmp_path)
    lock.write_text("a-crashed-process", "utf-8")
    old = time.time() - 600
    os.utime(lock, (old, old))

    secrets.save_refresh_token(REFRESH)

    assert secrets.read().refresh_token == REFRESH
    assert not lock.exists()


def test_FR003_a_lock_that_was_taken_over_is_not_removed_by_its_old_holder(
    tmp_path: Path,
) -> None:
    secrets = make(tmp_path)
    secrets.save_credentials(CLIENT_ID, CLIENT_SECRET)

    with secrets._locked():
        # another process judged us stale and took the lock over
        _lock_path(tmp_path).write_text("the-new-owner", "utf-8")

    assert _lock_path(tmp_path).read_text("utf-8") == "the-new-owner"
