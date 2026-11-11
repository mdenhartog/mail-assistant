# pure module (mutation-gated)
"""Rules of the request-code endpoint (U-web-settings-17): origin, username key and how long a request must wait."""

import hmac
from collections.abc import Iterable
from datetime import datetime, timedelta

_COMPARE = hmac.compare_digest  # skeleton


def origin_allowed(origin: str | None, public_origin: str) -> bool:
    """Return True only when the Origin header equals the public origin exactly."""
    raise NotImplementedError


def username_key(key: bytes, username: str) -> str:
    """Return the 64 lower-case hex characters of the keyed HMAC-SHA-256 of the username."""
    raise NotImplementedError


def same_key(first: str, second: str) -> bool:
    """Compare two username keys in constant time."""
    raise NotImplementedError


def wait_seconds(
    last_requested_at: datetime | None, sent_times: Iterable[datetime], now: datetime, cooldown: timedelta, cap: int
) -> int:
    """Return the whole seconds a new code request must wait (0 when it may proceed)."""
    raise NotImplementedError
