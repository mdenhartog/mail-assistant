# pure module (mutation-gated)
"""Time and attempt rules for the sign-in code (ADR-0036). No clock read, no I/O: `now` is a parameter."""

import math
from collections.abc import Iterable
from datetime import datetime, timedelta

_HOUR = timedelta(hours=1)


def _aware(*values: datetime) -> None:
    for value in values:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")


def code_expired(created_at: datetime, now: datetime, ttl: timedelta) -> bool:
    """Return True from the moment the code is `ttl` old."""
    _aware(created_at, now)
    return now - created_at >= ttl


def attempts_exhausted(attempts: int, max_attempts: int) -> bool:
    """Return True when no further comparison may be made."""
    return attempts >= max_attempts


def register_wrong(attempts: int, max_attempts: int) -> tuple[int, bool]:
    """Count one wrong attempt; return the new count and whether the code is now dead."""
    if attempts_exhausted(attempts, max_attempts):
        raise ValueError("attempts exhausted")
    new = attempts + 1
    return new, attempts_exhausted(new, max_attempts)


def cooldown_remaining(last_requested_at: datetime | None, now: datetime, cooldown: timedelta) -> int:
    """Whole seconds (rounded up) until a new code may be requested; counts every request, sent or not."""
    if last_requested_at is None:
        _aware(now)
        return 0
    _aware(last_requested_at, now)
    remaining = (last_requested_at + cooldown - now).total_seconds()
    return min(math.ceil(cooldown.total_seconds()), max(0, math.ceil(remaining)))


def hourly_cap_reached(sent_times: Iterable[datetime], now: datetime, cap: int) -> bool:
    """Return True when `cap` or more codes were sent within the last hour (failed sends are not in the list)."""
    _aware(now)
    count = 0
    for sent in sent_times:
        _aware(sent)
        if now - sent < _HOUR:
            count += 1
    return count >= cap
