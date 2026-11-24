"""What the model sees of a conversation (002m research R4, R10).

Only the newest ``WINDOW`` messages are sent. Every action result goes in as a data block whose
boundary is drawn at random per block, so text inside a result can never close it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

from hiretitan.platform.untrusted.delimit import delimit

WINDOW: Final = 30


def window[T](messages: Sequence[T], size: int = WINDOW) -> list[T]:
    return list(messages[-size:]) if size > 0 else []


def wrap_result(action: str, payload: Mapping[str, Any] | Sequence[Any]) -> str:
    """An action's result as a data block labelled with the action's name."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return delimit(action, body).text
