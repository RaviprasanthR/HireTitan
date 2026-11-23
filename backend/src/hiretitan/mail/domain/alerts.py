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
    # who gave the company and place: "fixed" (a site's reader) or "ai" (FR-013d)
    read_by: str = "fixed"


# Footer and notice words (FR-013c). An alert's footer is never a title, a company or a place,
# whoever read the email: a fixed reader whose layout guess runs past the last card, or the AI
# (seen on real LinkedIn alerts: "This email was intended for ...", "Learn why we included this").
FOOTER_WORDS = (
    "intended for",
    "you are receiving",
    "you received",
    "learn why",
    "why we included",
    "unsubscribe",
    "manage your",
    "manage alerts",
    "job alert",
    "privacy",
    "help center",
    "copyright",
    "this email",
    "notification",
    "view all",
    "see all",
)


def is_boilerplate(text: str) -> bool:
    """True for a line of an alert's footer or notices, in any letter case."""
    lower = " ".join(text.casefold().split())
    return any(words in lower for words in FOOTER_WORDS)
