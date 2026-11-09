"""Test helpers shared by the agent and the backend: a policy builder and a controllable clock."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from schedule_policy.policy import DEFAULT_POLICY, TimePolicy


def make_policy(**overrides: Any) -> TimePolicy:  # noqa: ANN401 - field overrides are checked by dataclasses.replace
    """The default policy with some fields replaced; an unknown field raises ``TypeError``."""
    return replace(DEFAULT_POLICY, **overrides)


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("a time zone is required")
    return moment


class FakeClock:
    """A clock that only moves when told to; always timezone-aware."""

    def __init__(self, start: datetime | None = None) -> None:
        """Start at ``start`` (default 2026-01-01T12:00:00Z); a naive start is refused."""
        self._now = _aware(start) if start is not None else datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        """The current fake moment."""
        return self._now

    def advance(self, delta: timedelta) -> datetime:
        """Move forward (or back with a negative delta) and return the new moment."""
        self._now += delta
        return self._now

    def set(self, moment: datetime) -> None:
        """Jump to ``moment``; a naive moment is refused."""
        self._now = _aware(moment)
