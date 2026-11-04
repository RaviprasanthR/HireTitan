"""Application settings the rest of the app may read (public API of the setup module)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class SettingsStore(Protocol):
    async def read_budget_cap(self) -> Decimal: ...

    async def write_budget_cap(self, cap: Decimal) -> None: ...


async def get_budget_cap(store: SettingsStore) -> Decimal:
    """The monthly AI budget cap in USD (FR-031); the default is 25.00."""
    return await store.read_budget_cap()


MAX_BUDGET_CAP = Decimal(10_000)


class BudgetCapInvalid(ValueError):
    """The cap is outside 0 to 10000 USD."""


class SpendReader(Protocol):
    async def spent_in_month(self, year: int, month: int) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class TierModel:
    tier: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class SettingsView:
    budget_cap_usd: Decimal
    spent_this_month_usd: Decimal
    tiers: tuple[TierModel, ...]
    key_status: str
    key_message: str | None


async def update_budget_cap(
    store: SettingsStore,
    value: Decimal,
    on_raised: Callable[[], Awaitable[None]],
) -> None:
    """Set the monthly cap (FR-031). Raising it wakes runs that paused on the budget."""
    if not value.is_finite() or not 0 <= value <= MAX_BUDGET_CAP:
        raise BudgetCapInvalid("The budget cap must be between 0 and 10000 USD")
    previous = await store.read_budget_cap()
    await store.write_budget_cap(value)
    if value > previous:
        await on_raised()
