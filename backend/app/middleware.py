"""Response headers, request id and the last-resort 500 answer."""

import logging

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import problem_response
from app.ids import IdSource

logger = logging.getLogger(__name__)

CONTENT_SECURITY_POLICY = "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
_FIXED_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


class HttpSurfaceMiddleware:
    """Pure ASGI middleware: request id, security headers on every response and the generic 500."""

    def __init__(self, app: ASGIApp, *, ids: IdSource) -> None:
        """Keep the next app and the id source."""
        self._app = app
        self._ids = ids

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one request; a client ``X-Request-Id`` is never read."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        request_id = self._ids.request_id()
        scope.setdefault("state", {})["request_id"] = request_id
        started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                for name, value in _FIXED_HEADERS.items():
                    headers[name] = value
                headers["X-Request-Id"] = request_id
                if headers.get("content-type", "").startswith("text/html"):
                    headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
            await send(message)

        try:
            await self._app(scope, receive, send_with_headers)
        except Exception as exc:
            # Only the class name is logged: the message and the trace may carry user data.
            logger.error("unhandled exception: %s", type(exc).__name__)
            if started:
                raise
            await problem_response(500)(scope, receive, send_with_headers)
