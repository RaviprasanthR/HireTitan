"""Model catalogue: tier -> model per provider, prices, and the cost calculator.

Data lives in ``models.yaml`` so a price change is a data change, not a code change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import yaml

from hiretitan.platform.llm.port import Tier, Usage

DEFAULT_CATALOG = Path(__file__).with_name("models.yaml")
_PER_MILLION = Decimal(1_000_000)


class UnknownModelError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class Price:
    """USD per 1M tokens."""

    input: Decimal
    cached_input: Decimal
    output: Decimal


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    prices_checked_on: date
    tiers: dict[str, dict[str, str]]  # provider -> tier -> model
    prices: dict[str, Price]  # model -> price

    @classmethod
    def load(cls, path: Path = DEFAULT_CATALOG) -> ModelCatalog:
        raw = cast(dict[str, Any], yaml.safe_load(path.read_text("utf-8")))
        providers = cast(dict[str, dict[str, Any]], raw["providers"])
        return cls(
            prices_checked_on=raw["prices_checked_on"],
            tiers={name: dict(p["tiers"]) for name, p in providers.items()},
            prices={
                model: Price(
                    Decimal(str(p["input"])),
                    Decimal(str(p["cached_input"])),
                    Decimal(str(p["output"])),
                )
                for provider in providers.values()
                for model, p in provider["models"].items()
            },
        )

    def model_for(self, provider: str, tier: Tier) -> str:
        try:
            return self.tiers[provider][tier]
        except KeyError:
            raise UnknownModelError(f"No model for provider {provider!r}, tier {tier!r}") from None

    def price(self, model: str) -> Price:
        try:
            return self.prices[model]
        except KeyError:
            raise UnknownModelError(f"No price for model {model!r}") from None

    def cost(self, model: str, usage: Usage) -> Decimal:
        price = self.price(model)
        fresh_input = usage.input_tokens - usage.cached_input_tokens
        total = (
            fresh_input * price.input
            + usage.cached_input_tokens * price.cached_input
            + usage.output_tokens * price.output
        )
        return total / _PER_MILLION
