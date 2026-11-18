"""Cleaning for ``extract_job_keywords`` v1: trim, drop repeats and drop instruction-like items.

The items come from an untrusted job description and are later handed to drafting prompts, so an
item that looks like an instruction to an AI, holds a link or spans lines is dropped here
(second-order injection, spec FR-021).
"""

from __future__ import annotations

import re
from typing import Any, Final

from hiretitan.platform.untrusted.screen import screen

# Not bare domains: ASP.NET and socket.io are technologies.
_LINK: Final = re.compile(r"https?://|www\.", re.I)


def _unsafe(text: str) -> bool:
    if "\n" in text or _LINK.search(text):
        return True
    return any(flag.severity != "low" for flag in screen(text))


def _tidy(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for item in items:
        if "\n" in item:
            continue
        text = " ".join(item.split())
        if text and not _unsafe(text) and text.casefold() not in seen:
            seen.add(text.casefold())
            kept.append(text)
    return kept[:limit]


def tidy(output: Any) -> Any:
    """The same output with trimmed, de-duplicated and screened lists."""
    summary = " ".join(output.role_summary.split())
    return type(output)(
        role_summary="" if _unsafe(summary) else summary,
        keywords=_tidy(output.keywords, 30),
        must_have=_tidy(output.must_have, 10),
    )
