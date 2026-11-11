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
        raise NotImplementedError


def limit(bucket: str) -> Callable[[Request], Awaitable[None]]:
    """Return a FastAPI dependency that checks the application's guard for the bucket."""
    raise NotImplementedError
