"""Delete all my data: back to the first-run state (FR-035, US4 scenario 2, SC-008).

Order matters. Open runs are cancelled first so nothing keeps working on data that is about to
go. The database is then emptied and its defaults put back in one transaction, so the app never
has an empty settings table. Stored files go after that, and last the provider key is checked
again. ``.env`` is never touched: the API key stays where the user put it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

_log = logging.getLogger(__name__)


class DeleteAllStore(Protocol):
    async def cancel_open_runs(self) -> None:
        """Cancel every run that has not ended, and save."""
        ...

    async def wipe_and_reseed(self) -> None:
        """Empty every table the app owns (including job queue and checkpoints), restore the
        fresh-install rows (default settings, provider status ``unknown``), in one transaction."""
        ...


class FileWiper(Protocol):
    def delete_all(self) -> None: ...


async def _nothing() -> None:
    return None


async def delete_all(
    *,
    store: DeleteAllStore,
    storage: FileWiper,
    enqueue_key_check: Callable[[], Awaitable[None]],
    forget_secrets: Callable[[], None] = lambda: None,
    disconnect_mail: Callable[[], Awaitable[object]] = _nothing,
) -> None:
    # Gmail first: stop a running check and hand the access back to Google, so no grant outlives
    # the data (FR-027). Google not answering never stops the delete; the token goes anyway.
    try:
        await disconnect_mail()
    except Exception:
        _log.warning("Gmail could not be disconnected first; its data is removed anyway.")
    await store.cancel_open_runs()
    await store.wipe_and_reseed()
    storage.delete_all()
    try:
        # file locks and disk I/O must not hold the API's event loop
        await asyncio.to_thread(forget_secrets)
    finally:
        await enqueue_key_check()
