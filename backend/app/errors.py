"""Problem responses (``application/problem+json``) with generic titles.

A body carries only ``type``, ``title`` and ``status``: never a message, a class name, a field or a client.
"""

from collections.abc import Mapping
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"

_TITLES: dict[int, str] = {
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    405: "Method not allowed",
    413: "Payload too large",
    415: "Unsupported media type",
    422: "Unprocessable content",
    429: "Too many requests",
    500: "Internal server error",
}
_FALLBACK_TITLE = "Error"


class ProblemError(Exception):
    """A refusal that is answered with a generic problem of the given status."""

    def __init__(self, status: int) -> None:
        """Remember the status."""
        super().__init__(status)
        self.status = status


class RateLimited(Exception):  # noqa: N818 - named after the 429 condition it signals
    """A limit was hit; the client may retry after the given number of seconds."""

    def __init__(self, retry_after_seconds: int) -> None:
        """Remember the wait."""
        super().__init__(retry_after_seconds)
        self.retry_after_seconds = retry_after_seconds


def problem_response(status: int, headers: Mapping[str, str] | None = None) -> JSONResponse:
    """Build the generic problem response for a status.

    Args:
        status: The HTTP status.
        headers: Extra headers, such as ``Retry-After`` or ``Allow``.

    Returns:
        A ``application/problem+json`` response with a generic title.
    """
    body = {"type": "about:blank", "title": _TITLES.get(status, _FALLBACK_TITLE), "status": status}
    return JSONResponse(body, status_code=status, headers=dict(headers or {}), media_type=PROBLEM_MEDIA_TYPE)


async def _on_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    error = cast("StarletteHTTPException", exc)
    allow = (error.headers or {}).get("Allow")
    return problem_response(error.status_code, {"Allow": allow} if allow else None)


async def _on_problem(_request: Request, exc: Exception) -> JSONResponse:
    error = cast("ProblemError", exc)
    return problem_response(error.status)


async def _on_invalid_request(_request: Request, _exc: Exception) -> JSONResponse:
    # The default body echoes the rejected input; the generic problem names neither field nor value.
    return problem_response(422)


async def _on_rate_limited(_request: Request, exc: Exception) -> JSONResponse:
    error = cast("RateLimited", exc)
    return problem_response(429, {"Retry-After": str(int(error.retry_after_seconds))})


def install_error_handlers(app: FastAPI) -> None:
    """Register the problem handlers on the application.

    Args:
        app: The application to register on.
    """
    app.add_exception_handler(StarletteHTTPException, _on_http_exception)
    app.add_exception_handler(ProblemError, _on_problem)
    app.add_exception_handler(RequestValidationError, _on_invalid_request)
    app.add_exception_handler(RateLimited, _on_rate_limited)
