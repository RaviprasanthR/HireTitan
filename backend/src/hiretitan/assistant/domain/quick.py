"""Quick actions (002m FR-029, amended 2026-11-24): what the chat offers first.

Each one opens a small form in the chat; the form's answers run HireTitan's own actions, so the
chat makes no AI call for them. Pure: the application layer runs them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Form = Literal["draft", "status", "paste"]
DraftKind = Literal["connection_request", "referral_message", "email"]
Status = Literal["applied", "inquired", "not_applied", "not_inquired"]


@dataclass(frozen=True, slots=True)
class QuickAction:
    key: str
    label: str
    form: Form
    draft_kind: DraftKind | None = None


QUICK_ACTIONS: Final[tuple[QuickAction, ...]] = (
    QuickAction("linkedin_request", "LinkedIn connection message", "draft", "connection_request"),
    QuickAction("linkedin_message", "LinkedIn message", "draft", "referral_message"),
    QuickAction("email", "Email", "draft", "email"),
    QuickAction("update_status", "Update a job's status", "status"),
    QuickAction("add_job", "Add a job", "paste"),
)

DRAFT_LABEL: Final[dict[str, str]] = {
    a.draft_kind: a.label for a in QUICK_ACTIONS if a.draft_kind is not None
}

# a status the form offers -> the catalogue action that sets it, and how it reads
STATUS_ACTION: Final[dict[str, tuple[str, str]]] = {
    "applied": ("mark_applied", "applied"),
    "inquired": ("mark_inquired", "inquired"),
    "not_applied": ("unmark_applied", "not applied"),
    "not_inquired": ("unmark_inquired", "not inquired"),
}
