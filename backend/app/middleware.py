"""Response headers, request id and the last-resort 500 answer."""

from starlette.types import ASGIApp, Receive, Scope, Send

from app.ids import IdSource


class HttpSurfaceMiddleware:
    """Pure ASGI middleware for the headers every response carries."""

    def __init__(self, app: ASGIApp, *, ids: IdSource) -> None:
        """Keep the next app and the id source."""
        raise NotImplementedError

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one request."""
        raise NotImplementedError
