"""Hosts the app may call out to (constitution I: the app never sends anything).

Every HTTP or AI client must be built with ``base_url=allowed_base_url(<host>)``
or a literal URL on one of these hosts; ``tests/architecture/test_no_send.py``
checks this statically. Adding a host is a reviewed change to this file.
"""

from __future__ import annotations

from typing import Final

# api.openai.com: the AI provider. The two Google hosts are for the read-only mail reader
# (feature 002c): the sign-in token endpoint and the Gmail API. Only two modules under
# ``hiretitan/mail/infra`` may call them, each held to its verbs by test_no_send.py.
ALLOWED_HOSTS: Final[frozenset[str]] = frozenset(
    {"api.openai.com", "gmail.googleapis.com", "oauth2.googleapis.com"}
)


class OutboundHostNotAllowedError(ValueError):
    """Raised when code asks for a base URL on a host that is not allowlisted."""

    def __init__(self, host: str) -> None:
        super().__init__(f"Outbound host is not allowlisted: {host!r}")
        self.host = host


def allowed_base_url(host: str, path: str = "/v1") -> str:
    """Return ``https://<host><path>`` if ``host`` is allowlisted, else raise."""
    if host not in ALLOWED_HOSTS:
        raise OutboundHostNotAllowedError(host)
    return f"https://{host}{path}"
