"""Bearer-token check as pure ASGI middleware (no framework state, constant-time compare)."""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send


class BearerAuthMiddleware:
    """Reject every HTTP request without the expected bearer token, except the health path."""

    def __init__(self, app: ASGIApp, token: str, open_paths: frozenset[str] = frozenset({"/ping"})) -> None:
        """Wrap ``app``; ``token`` is compared in constant time."""
        self._app = app
        self._token = token.encode()
        self._open_paths = open_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass lifespan through, refuse websockets, and require the bearer token for every HTTP path but health."""
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        elif scope["type"] == "http" and not self._allowed(scope):
            response = Response("unauthorized", status_code=401, headers={"WWW-Authenticate": "Bearer"})
            await response(scope, receive, send)
        else:
            await self._app(scope, receive, send)

    def _allowed(self, scope: Scope) -> bool:
        return scope["path"] in self._open_paths or self._authorised(scope)

    def _authorised(self, scope: Scope) -> bool:
        headers: dict[bytes, bytes] = dict(scope["headers"])
        scheme, _, value = headers.get(b"authorization", b"").decode("latin-1").partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(value.encode(), self._token)
