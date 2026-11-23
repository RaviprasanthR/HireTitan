"""Refuse a request that changes something when the browser says another site sent it.

HireTitan has no login, so any web page the person visits could otherwise send a "simple"
cross-site POST to ``localhost`` (no preflight; FastAPI reads a body with no content type as JSON)
and, say, delete all their data. Browsers mark every such request: ``Origin`` names the page's
site and ``Sec-Fetch-Site`` says ``cross-site`` or ``same-site``. A request with neither header
does not come from a web page (scripts, tests, the CLI tools) and is let through, as are reads:
a GET changes nothing (Google's sign-in comes back to the callback as a cross-site GET).
"""

from __future__ import annotations

from typing import Final

from starlette.types import ASGIApp, Receive, Scope, Send

from hiretitan.platform.web.problems import problem

UNSAFE: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})
FOREIGN_FETCH: Final = frozenset({b"cross-site", b"same-site"})
MESSAGE: Final = "Only HireTitan's own page can make this change."


def _origin_matches(origin: bytes, host: bytes | None) -> bool:
    """``Origin`` is ``scheme://host[:port]``; it must name the address the request was sent to."""
    scheme, sep, rest = origin.partition(b"://")
    if not sep or scheme not in (b"http", b"https") or host is None:
        return False
    return rest.lower() == host.lower()


class CrossSiteGuardMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in UNSAFE:
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        origin = headers.get(b"origin")
        fetch_site = headers.get(b"sec-fetch-site", b"").lower()
        foreign = fetch_site in FOREIGN_FETCH or (
            origin is not None and not _origin_matches(origin, headers.get(b"host"))
        )
        if foreign:
            await problem(403, MESSAGE)(scope, receive, send)
            return
        await self.app(scope, receive, send)
