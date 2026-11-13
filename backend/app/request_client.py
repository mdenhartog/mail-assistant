"""The client key of a request, next to the pure address rules of ``app.clientaddr`` (U-web-settings-60)."""

from typing import TYPE_CHECKING

from fastapi import Request

from app import clientaddr

if TYPE_CHECKING:
    from app.config import Settings


def client_key(request: Request) -> str:
    """Return the client key of the request: the address the last trusted proxy appended, else the peer's own.

    Args:
        request: The request; the app settings name the trusted proxies.

    Returns:
        The client key (see ``app.clientaddr``).
    """
    settings: Settings = request.app.state.settings
    forwarded = ",".join(request.headers.getlist("x-forwarded-for")) or None
    peer = request.client.host if request.client else None
    return clientaddr.client_key(peer, forwarded, settings.trusted_proxy_cidrs, settings.trusted_proxy_hops)
