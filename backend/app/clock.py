from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current time; the only place the app reads the wall clock."""

    def now(self) -> datetime:
        """Return the current time as an aware UTC datetime."""
        ...


class SystemClock:
    """Production clock."""

    def now(self) -> datetime:
        """Return the current time as an aware UTC datetime."""
        return datetime.now(UTC)
