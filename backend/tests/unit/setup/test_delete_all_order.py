"""Delete all my data, step order (002c final review): Gmail is handed back to Google first, the
secrets files are removed off the event loop, and the key check is queued even if that fails."""

from __future__ import annotations

import threading

import pytest

from hiretitan.setup.application.delete_all import delete_all


class Store:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def cancel_open_runs(self) -> None:
        self.log.append("cancel")

    async def wipe_and_reseed(self) -> None:
        self.log.append("wipe")


class Files:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def delete_all(self) -> None:
        self.log.append("files")


async def test_FR027_gmail_is_disconnected_first_then_everything_goes() -> None:
    log: list[str] = []

    async def disconnect() -> None:
        log.append("disconnect")

    async def key_check() -> None:
        log.append("key_check")

    await delete_all(
        store=Store(log),
        storage=Files(log),
        enqueue_key_check=key_check,
        forget_secrets=lambda: log.append("secrets"),
        disconnect_mail=disconnect,
    )

    assert log == ["disconnect", "cancel", "wipe", "files", "secrets", "key_check"]


async def test_FR027_google_not_answering_does_not_stop_the_delete() -> None:
    log: list[str] = []

    async def disconnect() -> None:
        raise RuntimeError("Google did not answer")

    async def key_check() -> None:
        log.append("key_check")

    await delete_all(
        store=Store(log),
        storage=Files(log),
        enqueue_key_check=key_check,
        forget_secrets=lambda: log.append("secrets"),
        disconnect_mail=disconnect,
    )

    assert log == ["cancel", "wipe", "files", "secrets", "key_check"]


async def test_secrets_are_removed_off_the_event_loop() -> None:
    threads: list[bool] = []

    async def key_check() -> None:
        return None

    await delete_all(
        store=Store([]),
        storage=Files([]),
        enqueue_key_check=key_check,
        forget_secrets=lambda: threads.append(
            threading.current_thread() is threading.main_thread()
        ),
    )

    assert threads == [False]


async def test_a_secrets_file_that_cannot_be_removed_still_queues_the_key_check() -> None:
    log: list[str] = []

    async def key_check() -> None:
        log.append("key_check")

    def busy() -> None:
        raise OSError("The Google secrets file is busy.")

    with pytest.raises(OSError, match="busy"):
        await delete_all(
            store=Store(log), storage=Files(log), enqueue_key_check=key_check, forget_secrets=busy
        )

    assert log == ["cancel", "wipe", "files", "key_check"]
