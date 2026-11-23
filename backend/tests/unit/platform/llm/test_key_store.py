"""T051: the AI key saved from Settings (FR-029, FR-030, SC-010)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from hiretitan.platform.llm.key_store import KeyStore, KeyStoreError
from hiretitan.platform.security.logging import configure_logging

KEY = "sk-test-0123456789abcdefghij"
OTHER = "sk-test-zyxwvutsrqponmlkjihg"


def store(tmp_path: Path, env_key: str | None = None) -> KeyStore:
    return KeyStore(tmp_path / "secrets" / "llm.json", SecretStr(env_key) if env_key else None)


def test_FR029_round_trip_and_atomic(tmp_path: Path) -> None:
    keys = store(tmp_path)
    assert keys.current() == (None, "none")

    keys.save(KEY)

    assert keys.current() == (KEY, "page")
    path = tmp_path / "secrets" / "llm.json"
    assert json.loads(path.read_text("utf-8")) == {"openai_api_key": KEY}
    assert not list(path.parent.glob("*.tmp"))  # written through a temporary file, then moved
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0  # owner-only


def test_FR029_replace_and_remove(tmp_path: Path) -> None:
    keys = store(tmp_path)
    keys.save(KEY)

    keys.save(OTHER)
    assert keys.current() == (OTHER, "page")

    keys.remove()
    assert keys.current() == (None, "none")
    keys.remove()  # removing nothing is fine


def test_FR029_env_wins(tmp_path: Path) -> None:
    keys = store(tmp_path, env_key=KEY)
    assert keys.current() == (KEY, "env")
    assert keys.from_environment

    with pytest.raises(KeyStoreError):
        keys.save(OTHER)
    with pytest.raises(KeyStoreError):
        keys.remove()


def test_FR029_never_in_repr(tmp_path: Path) -> None:
    keys = store(tmp_path)
    keys.save(KEY)

    assert KEY not in repr(keys)
    assert KEY not in str(keys)


def test_FR030_a_new_key_is_seen_without_restart(tmp_path: Path) -> None:
    api, worker = store(tmp_path), store(tmp_path)  # two processes, one file
    assert worker.current() == (None, "none")

    api.save(KEY)
    assert worker.current() == (KEY, "page")

    api.save(OTHER)
    assert worker.current() == (OTHER, "page")

    api.remove()
    assert worker.current() == (None, "none")


def test_a_damaged_file_counts_as_no_key(tmp_path: Path) -> None:
    path = tmp_path / "secrets" / "llm.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", "utf-8")

    assert store(tmp_path).current() == (None, "none")


def test_SC010_a_key_saved_later_is_redacted_in_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    configure_logging(())
    keys = store(tmp_path)
    keys.save(KEY)

    handler = logging.getLogger().handlers[0]
    record = logging.LogRecord("x", logging.WARNING, __file__, 1, f"calling with {KEY}", None, None)

    assert KEY not in handler.format(record)


def test_SC010_a_key_read_from_the_file_by_another_process_is_redacted_too(
    tmp_path: Path,
) -> None:
    store(tmp_path).save(KEY)
    configure_logging(())
    worker = store(tmp_path)

    worker.current()

    handler = logging.getLogger().handlers[0]
    record = logging.LogRecord("x", logging.WARNING, __file__, 1, f"key={KEY}", None, None)
    assert KEY not in handler.format(record)


@pytest.mark.parametrize(
    "bad", ["", "short", "sk-has a space-0123456789", "x" * 301, "sk-\n12345678901234567"]
)
def test_FR029_a_key_of_the_wrong_shape_is_refused(tmp_path: Path, bad: str) -> None:
    with pytest.raises(KeyStoreError):
        store(tmp_path).save(bad)
