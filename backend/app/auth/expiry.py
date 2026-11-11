# pure module (mutation-gated)
"""Session expiry: 30 minutes idle, 12 hours absolute (ADR-0036). No clock read, no I/O."""

from datetime import datetime, timedelta

IDLE = timedelta(minutes=30)
ABSOLUTE = timedelta(hours=12)


def _aware(*values: datetime) -> None:
    for value in values:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")


def idle_expired(last_seen_at: datetime, now: datetime) -> bool:
    """Return True from the moment the session has been idle for 30 minutes."""
    _aware(last_seen_at, now)
    return now - last_seen_at >= IDLE


def absolute_expired(created_at: datetime, now: datetime) -> bool:
    """Return True from the moment the session is 12 hours old, whatever the activity."""
    _aware(created_at, now)
    return now - created_at >= ABSOLUTE


def next_idle_expiry(now: datetime, created_at: datetime) -> datetime:
    """Return the new expiry after activity at `now`: 30 minutes on, never beyond the absolute limit."""
    _aware(now, created_at)
    return min(now + IDLE, created_at + ABSOLUTE)
