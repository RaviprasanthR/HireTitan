"""Messages that look like a pasted job posting (002m FR-021, research R4).

Such a message is not sent to the AI: the panel offers to move it into the paste dialog, where
it is handled as untrusted outside text. A short message is the person's own words.
"""

from __future__ import annotations

import re
from typing import Final

POSTING_MIN_CHARS: Final = 600
_HEADINGS: Final = re.compile(
    r"^\s*(?:#+\s*)?(?:key\s+)?("
    r"responsibilities|requirements|qualifications|about the role|about the job|"
    r"about us|what you[\u2019']?ll do|what you will do|what we offer|benefits|"
    r"who you are|must have|nice to have|job description|skills required"
    r")\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def looks_like_posting(text: str) -> bool:
    """Over 600 characters with two or more different posting headings on their own lines."""
    if len(text) <= POSTING_MIN_CHARS:
        return False
    found = {match.group(1).lower() for match in _HEADINGS.finditer(text)}
    return len(found) >= 2
