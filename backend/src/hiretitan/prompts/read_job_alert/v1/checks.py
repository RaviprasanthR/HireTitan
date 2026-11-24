"""Business checks for ``read_job_alert`` v1 that the schema cannot express.

``rule_errors(link_count)`` builds the ``TaskSpec.rules`` callable: a job may name only a link that
was in the list the AI was shown, and each link only once.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def rule_errors(link_count: int) -> Callable[[Any], list[str]]:
    def check(output: Any) -> list[str]:
        errors: list[str] = []
        seen: set[int] = set()
        for job in output.jobs:
            if job.link_index > link_count:
                errors.append(
                    f"The link {job.link_index} for {job.title!r} is not in the list of links. "
                    f"Use a number from 1 to {link_count}, or leave the job out."
                )
            elif job.link_index in seen:
                errors.append(f"Use the link {job.link_index} for one job only: list it once.")
            seen.add(job.link_index)
        return errors

    return check
