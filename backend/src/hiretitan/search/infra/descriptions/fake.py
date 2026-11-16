"""A description reader for end-to-end runs (``HIRETITAN_CAREER_OPS=fake``): no network.

The texts come from ``descriptions.json`` in the fake career-ops folder: ``{"<posting link>":
"<its text>"}``. A link that is not in the file cannot be read.
"""

from __future__ import annotations

import json
from pathlib import Path

from hiretitan.search.application.ports import DescribeRequest, DescriptionResult


class FileDescriptions:
    def __init__(self, directory: Path | None) -> None:
        self._path = None if directory is None else directory / "descriptions.json"

    async def read(self, job: DescribeRequest) -> DescriptionResult:
        texts: dict[str, str] = {}
        if self._path is not None:
            try:
                texts = json.loads(self._path.read_text("utf-8"))
            except (OSError, ValueError):
                texts = {}
        text = texts.get(job.url)
        if not text:
            return DescriptionResult("unreadable", error="no text for this link")
        return DescriptionResult("read", text)
