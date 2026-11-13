"""Response headers, request id, the body limit and the last-resort 500 answer."""

import logging

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import problem_response
from app.ids import IdSource

logger = logging.getLogger(__name__)
access_logger = logging.getLogger("app.access")

# The API serves data only: nothing may load or frame from it.
API_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'"
# The interactive docs (development and test only) load Swagger UI from a CDN and run an inline script.
DOCS_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src https://cdn.jsdelivr.net 'unsafe-inline'; img-src data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
DOCS_PAGE_PATHS = frozenset({"/docs", "/docs/oauth2-redirect"})
_FIXED_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def _log_request(scope: Scope, status: int, request_id: str) -> None:
    """Log one request line: method, matched path template, status, request id; never the query or the raw path."""
    template = getattr(scope.get("route"), "path", None) or "unmatched"
    access_logger.info(
        "request method=%s route=%s status=%d request_id=%s", scope["method"], template, status, request_id
    )


class HttpSurfaceMiddleware:
    """Pure ASGI middleware: request id, security headers on every response and the generic 500."""

    def __init__(self, app: ASGIApp, *, ids: IdSource, docs_enabled: bool) -> None:
        """Keep the next app, the id source and whether the docs pages exist (they need their own policy)."""
        self._app = app
        self._ids = ids
        self._docs_pages = DOCS_PAGE_PATHS if docs_enabled else frozenset[str]()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one request; a client ``X-Request-Id`` is never read."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        request_id = self._ids.request_id()
        scope.setdefault("state", {})["request_id"] = request_id
        started = False
        policy = DOCS_CONTENT_SECURITY_POLICY if scope["path"] in self._docs_pages else API_CONTENT_SECURITY_POLICY

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                _log_request(scope, message["status"], request_id)
                headers = MutableHeaders(scope=message)
                for name, value in _FIXED_HEADERS.items():
                    headers[name] = value
                headers["X-Request-Id"] = request_id
                headers["Content-Security-Policy"] = policy
            await send(message)

        try:
            await self._app(scope, receive, send_with_headers)
        except Exception as exc:
            # Only the class name and request id are logged: the message and the trace may carry user data.
            logger.error("unhandled exception class=%s request_id=%s", type(exc).__name__, request_id)
            if started:
                raise
            await problem_response(500)(scope, receive, send_with_headers)


class BodyLimitMiddleware:
    """Pure ASGI middleware: a body over the limit is refused with 413 before it is parsed (AC-16).

    A declared ``Content-Length`` over the limit is refused without calling the app. A body without a length
    (chunked) is counted as it is read and refused with 413 the moment it passes the limit.
    """

    def __init__(self, app: ASGIApp, *, limit_bytes: int) -> None:
        """Keep the next app and the limit from the settings."""
        self._app = app
        self._limit = limit_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one request, refusing it when its body is too big."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            if not declared.isascii() or not declared.isdigit():
                await problem_response(400)(scope, receive, send)
                return
            if int(declared) > self._limit:
                await problem_response(413)(scope, receive, send)
                return
        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._limit:
                    raise HTTPException(status_code=413)
            return message

        await self._app(scope, counting_receive, send)
