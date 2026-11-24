"""The fixed alert readers, one per built-in site (research R4).

Pure functions: a flattened email in, alert jobs out, nothing fetched. A reader that does not
recognise the layout returns nothing; the email is then left to the AI fallback or counted as one
that could not be read (FR-017)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Final

from hiretitan.mail.domain.alerts import AlertJob
from hiretitan.mail.domain.mime import Flat
from hiretitan.mail.domain.readers import cutshort, foundit, indeed, instahyre, linkedin, naukri

Reader = Callable[[Flat, datetime], list[AlertJob]]

READERS: Final[dict[str, Reader]] = {
    "linkedin": linkedin.read,
    "naukri": naukri.read,
    "indeed": indeed.read,
    "foundit": foundit.read,
    "instahyre": instahyre.read,
    "cutshort": cutshort.read,
}


def read_alert(site: str, flat: Flat, alert_date: datetime) -> list[AlertJob]:
    """The jobs the site's fixed reader finds; ``[]`` for a site with no reader (``other``)."""
    reader = READERS.get(site)
    return reader(flat, alert_date) if reader is not None else []
