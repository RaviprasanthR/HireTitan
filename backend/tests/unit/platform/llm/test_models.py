"""T019: the model catalogue (tier -> model, prices) and the cost calculator."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hiretitan.platform.llm.models import ModelCatalog, UnknownModelError
from hiretitan.platform.llm.port import Usage


def test_FR031_tier_resolves_to_model() -> None:
    catalog = ModelCatalog.load()
    assert catalog.model_for("openai", "fast") == "gpt-5.4-mini"
    assert catalog.model_for("openai", "strong") != catalog.model_for("openai", "fast")
    assert catalog.prices_checked_on <= datetime.now(UTC).date()


def test_cost_from_usage() -> None:
    catalog = ModelCatalog.load()
    price = catalog.price("gpt-5.4-mini")
    assert (price.input, price.cached_input, price.output) == (
        Decimal("0.75"),
        Decimal("0.075"),
        Decimal("4.50"),
    )
    # 1M input of which 400k were cached, plus 100k output:
    # 600k * 0.75 + 400k * 0.075 + 100k * 4.50, all per million = 0.45 + 0.03 + 0.45
    usage = Usage(input_tokens=1_000_000, cached_input_tokens=400_000, output_tokens=100_000)
    assert catalog.cost("gpt-5.4-mini", usage) == Decimal("0.93")


def test_cost_of_no_usage_is_zero() -> None:
    assert ModelCatalog.load().cost("gpt-5.4-mini", Usage()) == Decimal(0)


def test_unknown_model_rejected() -> None:
    catalog = ModelCatalog.load()
    with pytest.raises(UnknownModelError):
        catalog.price("gpt-nonexistent")
    with pytest.raises(UnknownModelError):
        catalog.model_for("openai", "medium")  # type: ignore[arg-type]
    with pytest.raises(UnknownModelError):
        catalog.model_for("acme", "fast")
