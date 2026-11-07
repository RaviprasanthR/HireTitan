"""Business checks for ``judge_relevance`` v2 that the schema cannot express (FR-028).

``rule_errors(refs, titles)`` builds the ``TaskSpec.rules`` callable: it lists what is wrong so
the validation chain can ask the model to repair its answer once. ``titles[i]`` is the posting
title of ``refs[i]``; a ``role`` may only use words that appear in that title.
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
_WORDS: Final = re.compile(r"\w+")


def role_words_outside(role: str, title: str) -> list[str]:
    """Words of ``role`` that the posting title does not contain."""
    allowed = {w.lower() for w in _WORDS.findall(title)}
    return [w for w in _WORDS.findall(role) if w.lower() not in allowed]


def rule_errors(expected_refs: list[str], titles: list[str]) -> Callable[[Any], list[str]]:
    title_of = dict(zip(expected_refs, titles, strict=True))

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
            if decision.role is not None and decision.ref in title_of:
                extra = role_words_outside(decision.role, title_of[decision.ref])
                if extra:
                    errors.append(
                        f"The role for {decision.ref} uses words not in its title: "
                        f"{', '.join(extra)}. Shorten the title; add nothing."
                    )
        return errors

    return check
