"""Company facts that the domain and every layer above it agree on."""

from __future__ import annotations

from typing import Final

COMPANY_ORIGINS: Final = ("built_in", "user")
RESOLUTIONS: Final = ("verified", "user_confirmed", "unresolved", "careers_page", "check_manually")
CHECK_RESULTS: Final = ("ok", "failed", "no_jobs", "blocked", "unreadable")
