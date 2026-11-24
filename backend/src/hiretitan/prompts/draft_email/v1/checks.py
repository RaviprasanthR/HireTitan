"""Business checks for ``draft_email`` v1 (002m): placeholders, contact details, tone, length.

``rule_errors(limit)`` builds the ``TaskSpec.rules`` callable. The text-level truthfulness checks
run in the workflow, after the names are filled in. The sign-off is the app's, never the model's.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Final

from hiretitan.drafts.domain.tone import check_tone

_PLACEHOLDER: Final = re.compile(r"\{[^{}]*\}")
_ALLOWED: Final = ("{recipient_first_name}",)
_CONTACT: Final = re.compile(r"https?://|www\.|@|\+?\d[\d ()-]{7,}", re.IGNORECASE)
SIGN_OFF: Final = "Best regards,\n{my_name}"


def assemble(subject: str, greeting: str, body: str, closing: str) -> str:
    """The whole email with its placeholders, the sign-off added by the app."""
    return f"Subject: {subject}\n\n{greeting}\n\n{body}\n\n{closing}\n\n{SIGN_OFF}"


def rule_errors(limit: int) -> Callable[[Any], list[str]]:
    def check(output: Any) -> list[str]:
        errors: list[str] = [
            f"Do not use {found} in the subject; it takes no placeholders."
            for found in _PLACEHOLDER.findall(output.subject)
        ]
        if re.search(r"\d", output.subject):
            errors.append("Do not put numbers in the subject.")
        whole = "\n".join((output.greeting, output.body, output.closing))
        for found in _PLACEHOLDER.findall(whole):
            if found not in _ALLOWED:
                errors.append(f"Do not use {found}; allowed: {', '.join(_ALLOWED)}.")
        if _CONTACT.search(output.subject + "\n" + whole):
            errors.append("Do not include links, email addresses or phone numbers.")
        errors.extend(problem.message for problem in check_tone(output.body, output.closing))
        text = assemble(output.subject, output.greeting, output.body, output.closing)
        if len(text) > limit:
            errors.append(f"The email is {len(text)} characters; keep it within {limit}.")
        return errors

    return check
