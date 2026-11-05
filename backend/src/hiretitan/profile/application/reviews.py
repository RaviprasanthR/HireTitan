"""Rules for working with a profile review (FR-016, FR-017, FR-018). Pure."""

from __future__ import annotations

from dataclasses import dataclass

from hiretitan.profile.domain.content import ProfileContent
from hiretitan.profile.domain.rules import RuleError, confirm_errors

CLOSED = "This review is already closed."
NOT_WAITING = "This review is not waiting for your answer."


class ReviewConflictError(Exception):
    """The review or its run is in a state that does not allow this action (HTTP 409)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ConfirmCheck:
    errors: list[RuleError]

    @property
    def ok(self) -> bool:
        return not self.errors


def check_confirm(content: ProfileContent) -> ConfirmCheck:
    """FR-018: can this content become a profile version? Drafts skip this check."""
    return ConfirmCheck(confirm_errors(content))


def require_open(status: str) -> None:
    if status != "open":
        raise ReviewConflictError(CLOSED)
