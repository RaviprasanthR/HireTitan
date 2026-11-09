"""Company facts that the domain and every layer above it agree on."""

from __future__ import annotations

from typing import Final, Literal

from hiretitan.search.domain.vendors import ENABLED_VENDORS

COMPANY_ORIGINS: Final = ("built_in", "user")
RESOLUTIONS: Final = ("verified", "user_confirmed", "unresolved", "careers_page", "check_manually")
CHECK_RESULTS: Final = ("ok", "failed", "no_jobs", "blocked", "unreadable")

BoardStatus = Literal["board", "careers_page", "check_manually", "unsupported", "unresolved"]


def board_status(
    ats_vendor: str | None, resolution: str, last_check_result: str | None
) -> BoardStatus:
    """How a company is read, in the words the company list shows (FR-016, FR-019)."""
    if resolution == "check_manually" or last_check_result in ("blocked", "unreadable"):
        return "check_manually"
    if ats_vendor:
        return "board" if ats_vendor in ENABLED_VENDORS else "unsupported"
    return "careers_page" if resolution == "careers_page" else "unresolved"
