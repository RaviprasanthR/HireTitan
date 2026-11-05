"""Which company job-board providers HireTitan may read (research R2, constitution VII).

A provider is added here only after its request paths were checked against the host's robots.txt
and recorded in the request allowlist. Keka is left out until that check is done.
"""

from __future__ import annotations

from typing import Final

ENABLED_VENDORS: Final = frozenset(
    {
        "greenhouse",
        "lever",
        "ashby",
        "workday",
        "smartrecruiters",
        "recruitee",
        "zoho_recruit",
        "amazon",
    }
)
