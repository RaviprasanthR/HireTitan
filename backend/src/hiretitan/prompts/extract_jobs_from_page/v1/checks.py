"""Business checks for ``extract_jobs_from_page`` v1 that the schema cannot express.

``rule_errors(host)`` builds the ``TaskSpec.rules`` callable. Every link must lead to the page's
own site: whatever the page says, it cannot send the app to another address (SC-011).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit


def _bare(host: str) -> str:
    return host.lower().removeprefix("www.")


def _same_site(link_host: str, page_host: str) -> bool:
    link_host, page_host = _bare(link_host), _bare(page_host)
    if not link_host:
        return False
    return (
        link_host == page_host
        or link_host.endswith("." + page_host)
        or ("." in link_host and page_host.endswith("." + link_host))
    )


def rule_errors(page_host: str) -> Callable[[Any], list[str]]:
    def check(output: Any) -> list[str]:
        errors: list[str] = []
        seen: set[str] = set()
        for job in output.jobs:
            parts = urlsplit(job.url)
            on_site = parts.scheme in ("http", "https") and _same_site(
                parts.hostname or "", page_host
            )
            if not on_site:
                errors.append(
                    f"The link for {job.title!r} is not a link on {page_host}. "
                    "Leave out jobs that do not link to this site."
                )
            elif job.url in seen:
                errors.append(f"List the link {job.url} once.")
            seen.add(job.url)
        return errors

    return check
