"""002i: SearchRules to and from the stored JSON, including the area of work (FR-030)."""

from __future__ import annotations

from hiretitan.search.domain.rules import RuleItem, SearchRules
from hiretitan.search.domain.rules_serialization import rules_from_dict, rules_to_dict


def test_FR030_old_rules_without_areas_read_as_empty() -> None:
    stored = {"title_words": [{"text": "Backend Engineer", "origin": "user"}], "max_age_days": 30}
    assert rules_from_dict(stored).areas == ()


def test_FR030_areas_round_trip() -> None:
    rules = SearchRules(
        title_words=(RuleItem("Backend Engineer", "user"),), areas=("back_end", "data")
    )
    data = rules_to_dict(rules)
    assert data["areas"] == ["back_end", "data"]
    assert rules_from_dict(data).areas == ("back_end", "data")
