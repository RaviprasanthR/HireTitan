"""Which company job-board providers HireTitan may read (research R2, constitution VII).

A provider is added here only after its request paths were checked against the host's robots.txt
and recorded in the request allowlist (``infra/careerops/allowlist.py``). Left out for now:
Keka (not yet checked) and SmartRecruiters (api.smartrecruiters.com/robots.txt disallows every
client except LinkedInBot, checked 2026-11-05). Companies on those boards show as "check manually".
"""

from __future__ import annotations

from typing import Final

ENABLED_VENDORS: Final = frozenset(
    {
        "greenhouse",
        "lever",
        "ashby",
        "workday",
        "recruitee",
        "zoho_recruit",
        "amazon",
    }
)
