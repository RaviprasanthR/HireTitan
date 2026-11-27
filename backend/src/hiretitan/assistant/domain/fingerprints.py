"""Fingerprints of the rows a confirm card will touch (002m research R7, EC-02).

A card stores one hash per target when it is proposed; confirming recomputes them, and any
difference means the item changed (or is gone) since, so the card expires instead of applying.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def fingerprint(fields: Mapping[str, Any]) -> str:
    """A stable SHA-256 of the fields: key order does not matter; dates and ids as text."""
    canonical = json.dumps(dict(fields), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stale_targets(saved: Mapping[str, str], current: Mapping[str, str]) -> list[str]:
    """Targets whose fingerprint changed, or that no longer exist, in a stable order."""
    return sorted(key for key, value in saved.items() if current.get(key) != value)
