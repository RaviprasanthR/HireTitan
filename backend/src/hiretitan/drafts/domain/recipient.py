"""Who a message is for (research R2). Pure.

The AI sees only the recipient's *kind*; the name is filled in by the workflow after the checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal
from uuid import UUID

RecipientKind = Literal["recruiter", "hiring_manager", "engineer", "other"]
KINDS: Final[tuple[RecipientKind, ...]] = ("recruiter", "hiring_manager", "engineer", "other")
NAME_MAX: Final = 120
ROLE_MAX: Final = 120
ALLOWED_PLACEHOLDERS: Final = ("{recipient_first_name}", "{my_name}")

_RULES: Final[tuple[tuple[RecipientKind, tuple[str, ...]], ...]] = (
    ("recruiter", ("talent", "recruit", "recruiter", "hr", "people partner", "sourcer")),
    ("hiring_manager", ("manager", "lead", "head", "director", "vp", "chief", "cto")),
    ("engineer", ("engineer", "developer", "architect", "sde", "programmer")),
)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")
_ANY_PLACEHOLDER = re.compile(r"\{[^{}]*\}")


@dataclass(frozen=True, slots=True)
class TypedRecipient:
    name: str
    role: str | None


def kind_from_role(role: str | None) -> RecipientKind:
    """The kind a role most likely means; the person can change it. Whole words only."""
    if not role:
        return "other"
    text = role.casefold()
    for kind, words in _RULES:
        for word in words:
            if re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", text):
                return kind
    return "other"


def _clean(value: str) -> str:
    return _SPACES.sub(" ", _CONTROL.sub(" ", value)).strip()


def clean_typed(name: str, role: str | None) -> TypedRecipient:
    """A typed name and role, trimmed and without control characters. Raises ValueError."""
    clean_name = _clean(name)
    clean_role = _clean(role) if role else ""
    if not 1 <= len(clean_name) <= NAME_MAX:
        raise ValueError(f"The name must be 1 to {NAME_MAX} characters.")
    if len(clean_role) > ROLE_MAX:
        raise ValueError(f"The role must be at most {ROLE_MAX} characters.")
    return TypedRecipient(clean_name, clean_role or None)


def first_name(name: str) -> str:
    """The first word of the name, nothing else: no surname is ever invented or added."""
    parts = _clean(name).split(" ")
    return parts[0] if parts and parts[0] else ""


def recipient_key(contact_id: UUID | None, name: str) -> str:
    return f"contact:{contact_id}" if contact_id else f"typed:{_clean(name).casefold()}"


def fill(template: str, recipient_first_name: str, my_name: str) -> str:
    """Put the real names where the two placeholders are; other braces stay as they are."""
    return template.replace("{recipient_first_name}", recipient_first_name).replace(
        "{my_name}", my_name
    )


def unknown_placeholders(template: str) -> list[str]:
    """Anything in braces other than the two allowed placeholders."""
    return [p for p in _ANY_PLACEHOLDER.findall(template) if p not in ALLOWED_PLACEHOLDERS]
