"""Request limits: routes declare ``limit(bucket)``; the in-process guard counts per client (ADR-0034)."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi import Request

from app.config import Settings
from app.core.security import AUTH_DEPENDENCY_MARKER, LIMIT_KIND
from app.errors import RateLimited
from app.limits import FixedWindowLimiter
from app.request_client import client_key


class LimitGuard(Protocol):
    """Decides whether a request may proceed; raises ``RateLimited`` when it may not."""

    async def check(self, bucket: str, request: Request) -> None:
        """Count the request against the bucket."""
        ...


class InProcessLimitGuard:
    """The real guard: fixed windows in memory, one counter per client and bucket (ADR-0034).

    The first refusal of a client in a window records one ``rate_limited`` event; the rest are refused without a
    database write, so a flood does not become database load.
    """

    def __init__(self, settings: Settings) -> None:
        """Take the limit and the window length from the settings, the only place that defines them."""
        self._limiter = FixedWindowLimiter(
            settings.rate_limit_per_minute, settings.rate_window_seconds, settings.rate_max_counters
        )

    async def check(self, bucket: str, request: Request) -> None:
        """Count the request against the bucket.

        Args:
            bucket: Name of the limit bucket.
            request: The request; its app holds the clock and, once attached, the event store.

        Raises:
            RateLimited: The client used up the bucket in this window.
        """
        state = request.app.state
        client = client_key(request)
        decision = self._limiter.hit(client, bucket, state.clock.now().timestamp())
        if decision.allowed:
            return
        events = getattr(state, "security_events", None)
        if decision.first_refusal and events is not None:
            await events.record("rate_limited", request.state.request_id, client)
        raise RateLimited(decision.retry_after)


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

    setattr(dependency, AUTH_DEPENDENCY_MARKER, LIMIT_KIND)  # read by the route inventory
    return dependency
