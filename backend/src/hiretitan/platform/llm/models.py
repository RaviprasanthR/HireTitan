"""Model catalogue: which model each tier uses, per provider.

Data lives in ``models.yaml`` so a model change is a data change, not a code change. HireTitan
keeps no prices: it shows no AI cost and has no budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from hiretitan.platform.llm.port import Tier

DEFAULT_CATALOG = Path(__file__).with_name("models.yaml")


class UnknownModelError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    tiers: dict[str, dict[str, str]]  # provider -> tier -> model

    @classmethod
    def load(cls, path: Path = DEFAULT_CATALOG) -> ModelCatalog:
        raw = cast(dict[str, Any], yaml.safe_load(path.read_text("utf-8")))
        providers = cast(dict[str, dict[str, Any]], raw["providers"])
        return cls(tiers={name: dict(p["tiers"]) for name, p in providers.items()})

    def model_for(self, provider: str, tier: Tier) -> str:
        try:
            return self.tiers[provider][tier]
        except KeyError:
            raise UnknownModelError(f"No model for provider {provider!r}, tier {tier!r}") from None
