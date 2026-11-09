"""The policy port and the one-notice-per-incident rule (C-9; ADR-0025)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from schedule_policy.policy import TimePolicy


class PolicySource(Protocol):
    """Where an operation gets the times it works with: one snapshot per operation."""

    async def current(self) -> TimePolicy:
        """The policy in force now; never raises, falls back to the last good values or the defaults."""
        ...


class Notifier(Protocol):
    """Telegram, sending a short plain-text note to Marco."""

    async def say(self, text: str) -> None:
        """Send the note."""
        ...


class PolicyNotice:
    """Tells Marco which values are in use when the stored ones cannot be used."""

    def __init__(self, notifier: Notifier) -> None:
        """Keep the notifier."""
        self._notifier = notifier
