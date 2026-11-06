"""The Home setup checklist (FR-028). Pure."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Checklist:
    key_ok: bool
    resume_uploaded: bool
    profile_confirmed: bool
    preferences_saved: bool
    rules_approved: bool = False
    searched_once: bool = False


def build_checklist(
    *,
    key_status: str,
    resume_uploaded: bool,
    profile_confirmed: bool,
    preferences_saved: bool,
    rules_approved: bool = False,
    searched_once: bool = False,
) -> Checklist:
    """The AI key step is done only when the provider says it works."""
    return Checklist(
        key_ok=key_status == "working",
        resume_uploaded=resume_uploaded,
        profile_confirmed=profile_confirmed,
        preferences_saved=preferences_saved,
        rules_approved=rules_approved,
        searched_once=searched_once,
    )
