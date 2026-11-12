"""T019: the model catalogue (tier -> model per provider). It keeps no prices."""

from __future__ import annotations

import pytest

from hiretitan.platform.llm.models import ModelCatalog, UnknownModelError


def test_FR031_tier_resolves_to_model() -> None:
    catalog = ModelCatalog.load()
    assert catalog.model_for("openai", "fast") == "gpt-5.4-mini"
    assert catalog.model_for("openai", "strong") != catalog.model_for("openai", "fast")


def test_FR011_the_catalogue_has_no_prices() -> None:
    catalog = ModelCatalog.load()

    assert not [name for name in dir(catalog) if "price" in name.lower() or "cost" in name.lower()]


def test_unknown_model_rejected() -> None:
    catalog = ModelCatalog.load()
    with pytest.raises(UnknownModelError):
        catalog.model_for("openai", "medium")  # type: ignore[arg-type]
    with pytest.raises(UnknownModelError):
        catalog.model_for("acme", "fast")
