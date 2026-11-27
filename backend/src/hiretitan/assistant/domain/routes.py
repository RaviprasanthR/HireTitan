"""The app's pages Mikasa may link to (``[[page:/path]]``), as in ``frontend/src/app/routes.tsx``.

A link to anything else is removed from her reply (research R9).
"""

from __future__ import annotations

from typing import Final

APP_ROUTES: Final = (
    "/",
    "/explore",
    "/profile",
    "/profile/preferences",
    "/profile/search-rules",
    "/profile/connections",
    "/profile/edit",
    "/profile/review/:reviewId",
    "/profile/versions",
    "/profile/versions/:versionId",
    "/companies",
    "/search/history",
    "/search/runs/:id",
    "/jobs/:id",
    "/jobs/:id/resume",
    "/review",
    "/settings",
    "/settings/:tab",
)
