"""RFC 9457 ``application/problem+json`` helpers shared by every API module."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Final

from fastapi.responses import JSONResponse

PROBLEM_JSON: Final = "application/problem+json"


class ProblemError(Exception):
    """Raise from a route to answer with a problem document; ``extra`` members are included
    (for example ``open_review_id`` on a 409)."""

    def __init__(self, status: int, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.extra = extra


def problem(
    status: int,
    detail: str,
    *,
    errors: list[dict[str, str]] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://httpstatuses.io/{status}",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
    }
    if errors is not None:
        body["errors"] = errors
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)
