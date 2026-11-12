"""The seam for request limits: routes declare it, a later unit supplies the real guard."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi import Request


class LimitGuard(Protocol):
    """Decides whether a request may proceed; raises ``RateLimited`` when it may not."""

    async def check(self, bucket: str, request: Request) -> None:
        """Count the request against the bucket."""
        ...


class NoopLimitGuard:
    """Default guard: lets every request through."""

    async def check(self, bucket: str, request: Request) -> None:
        """Do nothing."""


def limit(bucket: str) -> Callable[[Request], Awaitable[None]]:
    """Return a FastAPI dependency that checks the application's guard for the bucket.

    Args:
        bucket: Name of the limit bucket the route counts against.

    Returns:
        A dependency to put in ``dependencies=[Depends(limit("..."))]``.
    """

    async def dependency(request: Request) -> None:
        guard: LimitGuard = request.app.state.limit_guard
        await guard.check(bucket, request)

    return dependency


class InProcessLimitGuard:
    """The real guard: fixed windows in memory, one counter per client and bucket (ADR-0034)."""

    def __init__(self, limit_per_window: int, window_seconds: int) -> None:
        """Keep the limit and the window length from the settings."""
        raise NotImplementedError

    async def check(self, bucket: str, request: Request) -> None:
        """Count the request against the bucket."""
        raise NotImplementedError
