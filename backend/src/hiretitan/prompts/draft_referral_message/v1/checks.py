"""Business checks for ``draft_referral_message`` v1: placeholders, contact details, tone.

``rule_errors(limit)`` builds the ``TaskSpec.rules`` callable. The text-level truthfulness checks
run in the workflow, after the names are filled in.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Final

from hiretitan.drafts.domain.tone import check_tone

_PLACEHOLDER: Final = re.compile(r"\{[^{}]*\}")
_ALLOWED: Final = ("{recipient_first_name}", "{my_name}")
_CONTACT: Final = re.compile(r"https?://|www\.|@|\+?\d[\d ()-]{7,}", re.IGNORECASE)


def rule_errors(limit: int) -> Callable[[Any], list[str]]:
    def check(output: Any) -> list[str]:
        errors: list[str] = []
        whole = "\n".join((output.greeting, output.body, output.easy_out, output.sign_off))
        for found in _PLACEHOLDER.findall(whole):
            if found not in _ALLOWED:
                errors.append(f"Do not use {found}; allowed: {', '.join(_ALLOWED)}.")
        if _CONTACT.search(whole):
            errors.append("Do not include links, email addresses or phone numbers.")
        errors.extend(problem.message for problem in check_tone(output.body, output.easy_out))
        if len(whole) > limit:
            errors.append(f"The message is {len(whole)} characters; keep it within {limit}.")
        return errors

    return check
