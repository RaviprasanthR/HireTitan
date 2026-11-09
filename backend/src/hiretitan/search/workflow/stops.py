"""How a search ends early (US1 AS8/AS9, FR-010, FR-010a, FR-028).

After each batch is stored the graph asks two questions: did the AI stop being available for a
reason that will not pass on its own (budget reached, out of credit), and did the person press
Stop? Either ends the search with that outcome. Finished batches are kept and ``next_index``
points at the first company not read, so the next search carries on from there. A temporary
provider error is not a stop: the affected jobs are shown as "not checked by AI" and the search
goes on (FR-028).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from hiretitan.platform.llm.port import AiUnavailable

FINISHED: Final = "finished"
STOPPED_BY_USER: Final = "stopped_by_user"
BUDGET_REACHED: Final = "budget_reached"
OUT_OF_CREDIT: Final = "out_of_credit"
RUN_STOPS: Final = (BUDGET_REACHED, OUT_OF_CREDIT)


@dataclass(frozen=True, slots=True)
class Stop:
    outcome: str
    message: str | None = None


def stop_for(unavailable: AiUnavailable) -> Stop | None:
    """The stop an unavailable AI causes; ``None`` for a key problem (rules carry on, FR-028)."""
    if unavailable.reason == OUT_OF_CREDIT:
        return Stop(OUT_OF_CREDIT, unavailable.provider_message)
    if unavailable.reason == BUDGET_REACHED:
        return Stop(BUDGET_REACHED)
    return None
