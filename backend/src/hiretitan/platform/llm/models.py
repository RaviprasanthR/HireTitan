"""Model catalogue: which model each tier uses, per provider.

Data lives in ``models.yaml`` so a model change is a data change, not a code change. HireTitan
keeps no prices: it shows no AI cost and has no budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    # provider -> model -> what it can do ("tools", "streaming"); a model not listed has none
    capabilities: dict[str, dict[str, frozenset[str]]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = DEFAULT_CATALOG) -> ModelCatalog:
        raw = cast(dict[str, Any], yaml.safe_load(path.read_text("utf-8")))
        providers = cast(dict[str, dict[str, Any]], raw["providers"])
        return cls(
            tiers={name: dict(p["tiers"]) for name, p in providers.items()},
            capabilities={
                name: {
                    model: frozenset(caps)
                    for model, caps in cast(
                        dict[str, list[str]], p.get("capabilities") or {}
                    ).items()
                }
                for name, p in providers.items()
            },
        )

    def supports(self, provider: str, tier: Tier, capability: str) -> bool:
        """Whether the model behind ``tier`` can do ``capability`` (002m research R11)."""
        model = self.model_for(provider, tier)
        return capability in self.capabilities.get(provider, {}).get(model, frozenset())

    def model_for(self, provider: str, tier: Tier) -> str:
        try:
            return self.tiers[provider][tier]
        except KeyError:
            raise UnknownModelError(f"No model for provider {provider!r}, tier {tier!r}") from None
