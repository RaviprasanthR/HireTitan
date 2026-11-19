"""A few tries with a short wait, for answers that mean "try again" (429, 5xx, no connection).

Kept free of any HTTP library so only the two Google modules need to import one (FR-007).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final, Protocol

from hiretitan.mail.application.ports import MailUnavailableError

ATTEMPTS: Final = 3
RETRY_STATUSES: Final = frozenset({429, 500, 502, 503, 504})


class _HasStatus(Protocol):
    @property
    def status_code(self) -> int: ...


Sleep = Callable[[float], Awaitable[None]]


async def with_retries[R: _HasStatus](
    send: Callable[[], Awaitable[R]],
    sleep: Sleep,
    network_errors: tuple[type[Exception], ...],
) -> R:
    """The first answer that is not a "try again", or ``MailUnavailableError`` after 3 tries."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            answer = await send()
        except network_errors:
            if attempt == ATTEMPTS:
                raise MailUnavailableError("Google could not be reached.") from None
        else:
            if answer.status_code not in RETRY_STATUSES:
                return answer
            if attempt == ATTEMPTS:
                raise MailUnavailableError("Google is not answering right now.")
        await sleep(0.5 * attempt)
    raise MailUnavailableError("Google could not be reached.")  # pragma: no cover
