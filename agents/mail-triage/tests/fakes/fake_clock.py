"""A clock tests move by hand: no sleeping, no wall time. Usable as ``clock()``, ``clock.now()``, ``clock.today()``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


class FakeClock:
    """Shared fake clock; the time only changes through ``advance`` and ``set``."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("the fake clock needs a timezone")
        self._at = at.astimezone(UTC)

    def __call__(self) -> datetime:
        """The current fake time."""
        return self._at

    def now(self) -> datetime:
        """The current fake time."""
        return self._at

    def today(self) -> str:
        """The current UTC date as ``YYYY-MM-DD``."""
        return self._at.date().isoformat()

    def advance(self, by: timedelta) -> None:
        """Move the time forward."""
        self._at += by

    def set(self, at: datetime) -> None:
        """Jump to another time (also backwards, for clock-change tests)."""
        self._at = at.astimezone(UTC)
