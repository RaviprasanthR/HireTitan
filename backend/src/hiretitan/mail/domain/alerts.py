"""What an alert email yields: a job as the email gave it (FR-013). Pure.

Nothing here is guessed: a company or location the email does not give stays ``None``. The link is
kept as the email gave it; ``posting_id`` is the site's own number for the posting when the link
shows one (it is how a repeat is recognised, FR-022).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

TITLE_MAX = 200
COMPANY_MAX = 120
LOCATION_MAX = 120
LINK_MAX = 2000
JOBS_PER_EMAIL_MAX = 60


@dataclass(frozen=True, slots=True)
class AlertJob:
    title: str
    company: str | None
    location: str | None
    link: str
    posting_id: str | None
    site: str
    alert_date: datetime
    # the posting date, only when the alert states one (drives "may have closed", FR-020)
    posted_at: datetime | None = None
    injection_signals: list[dict[str, Any]] = field(default_factory=list)
