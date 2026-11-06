"""A career-ops stand-in for end-to-end runs (``HIRETITAN_CAREER_OPS=fake``): no Node, no network.

Each board is answered from ``<vendor>__<board_id>.json`` in the fake folder:
``{"postings": [{title, url, location, posted_at, description, requisition_id}]}`` or
``{"error": "message"}``. A board with no file has no jobs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from hiretitan.search.application.ports import (
    BoardRef,
    CompanyScan,
    DiscoveryResult,
    Posting,
    ScanError,
    ScanOk,
    ScanResult,
)


def _posting(raw: dict[str, Any]) -> Posting:
    posted = raw.get("posted_at")
    return Posting(
        title=str(raw["title"]),
        url=str(raw["url"]),
        location=raw.get("location"),
        posted_at=datetime.fromisoformat(posted) if posted else None,
        description=raw.get("description"),
        requisition_id=raw.get("requisition_id"),
    )


class FileCareerOps:
    def __init__(self, directory: Path | None) -> None:
        self._directory = directory

    def _read(self, ref: BoardRef) -> CompanyScan:
        if self._directory is None:
            return ScanOk([])
        path = self._directory / f"{ref.vendor}__{ref.board_id}.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except FileNotFoundError:
            return ScanOk([])
        except (OSError, ValueError) as error:
            return ScanError(f"Could not read the fake board file: {error}")
        if data.get("error"):
            return ScanError(str(data["error"]))
        return ScanOk([_posting(p) for p in data.get("postings", [])])

    async def scan(self, refs: list[BoardRef]) -> ScanResult:
        return {ref.company_id: self._read(ref) for ref in refs}

    async def discover(self, careers_url: str) -> DiscoveryResult | None:
        return None
