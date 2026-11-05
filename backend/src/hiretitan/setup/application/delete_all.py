"""Delete all my data: back to the first-run state (FR-035, US4 scenario 2, SC-008).

Order matters. Open runs are cancelled first so nothing keeps working on data that is about to
go. The database is then emptied and its defaults put back in one transaction, so the app never
has an empty settings table. Stored files go after that, and last the provider key is checked
again. ``.env`` is never touched: the API key stays where the user put it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol


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


async def delete_all(
    *,
    store: DeleteAllStore,
    storage: FileWiper,
    enqueue_key_check: Callable[[], Awaitable[None]],
) -> None:
    await store.cancel_open_runs()
    await store.wipe_and_reseed()
    storage.delete_all()
    await enqueue_key_check()
