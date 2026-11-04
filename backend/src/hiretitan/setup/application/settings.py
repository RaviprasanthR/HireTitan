"""Application settings the rest of the app may read (public API of the setup module)."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class SettingsStore(Protocol):
    async def read_budget_cap(self) -> Decimal: ...

    async def write_budget_cap(self, cap: Decimal) -> None: ...


async def get_budget_cap(store: SettingsStore) -> Decimal:
    """The monthly AI budget cap in USD (FR-031); the default is 25.00."""
    return await store.read_budget_cap()
