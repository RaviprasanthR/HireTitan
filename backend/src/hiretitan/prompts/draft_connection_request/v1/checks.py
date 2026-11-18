"""Business checks for ``draft_connection_request`` v1 that the schema cannot express.

``rule_errors(first_name, limit)`` builds the ``TaskSpec.rules`` callable. The real first name is
used only here, in code, to measure the length once it is filled in; it is never sent to the AI.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Final

_PLACEHOLDER: Final = re.compile(r"\{[^{}]*\}")
_ALLOWED: Final = ("{recipient_first_name}",)
_CONTACT: Final = re.compile(r"https?://|www\.|@|\+?\d[\d ()-]{7,}", re.IGNORECASE)


def rule_errors(first_name: str, limit: int) -> Callable[[Any], list[str]]:
    def check(output: Any) -> list[str]:
        errors: list[str] = []
        body: str = output.body
        for found in _PLACEHOLDER.findall(body):
            if found not in _ALLOWED:
                errors.append(f"Do not use {found}; the only placeholder allowed is {_ALLOWED[0]}.")
        if _CONTACT.search(body):
            errors.append("Do not include links, email addresses or phone numbers.")
        filled = body.replace(_ALLOWED[0], first_name)
        if len(filled) > limit:
            errors.append(
                f"The note is {len(filled)} characters with the name; keep it within {limit}."
            )
        return errors

    return check
