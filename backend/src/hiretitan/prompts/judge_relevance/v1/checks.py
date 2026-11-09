"""Business checks for ``judge_relevance`` v1 that the schema cannot express (FR-028).

``rule_errors(refs)`` builds the ``TaskSpec.rules`` callable: it lists what is wrong so the
validation chain can ask the model to repair its answer once.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from typing import Any, Final

_LINK: Final = re.compile(
    r"https?://|www\.|[\w.+-]+@[\w-]+\.\w+|"
    r"\b[a-z0-9-]+\.(?:com|net|org|io|in|co|dev|app|ai|xyz|info|biz|me|ly|cc)\b",
    re.IGNORECASE,
)


def rule_errors(expected_refs: list[str]) -> Callable[[Any], list[str]]:
    def check(output: Any) -> list[str]:
        errors: list[str] = []
        counts = Counter(d.ref for d in output.decisions)
        for ref in expected_refs:
            if counts[ref] == 0:
                errors.append(f"Missing a decision for {ref}.")
        for ref, count in counts.items():
            if ref not in expected_refs:
                errors.append(f"{ref} is not one of the jobs given.")
            elif count > 1:
                errors.append(f"Answer {ref} exactly once.")
        for decision in output.decisions:
            if _LINK.search(decision.reason):
                errors.append(f"The reason for {decision.ref} must not contain a link or address.")
        return errors

    return check
