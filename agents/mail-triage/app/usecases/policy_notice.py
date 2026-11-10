"""The policy port and the one-notice-per-incident rule (C-9; ADR-0025)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from app.core import settings_text

if TYPE_CHECKING:
    from schedule_policy.policy import TimePolicy

logger = logging.getLogger(__name__)


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


def notice_text(in_use: TimePolicy, reason: str) -> str:
    """Plain text naming the values the agent works with now: Marco needs to know what they are."""
    return (
        f"I cannot use your saved settings ({reason}). Until that is fixed I am using:\n"
        f"- Quiet hours: {settings_text.clock(in_use.quiet_start)} to {settings_text.clock(in_use.quiet_end)}\n"
        f"- Daily overview: {settings_text.clock(in_use.overview_at)}\n"
        f"- Remind-me-later default: {settings_text.clock(in_use.remind_at)}\n"
        f"- Time zone: {in_use.zone}"
    )


class PolicyNotice:
    """Tells Marco which values are in use when the stored ones cannot be used: once per incident.

    An incident lasts from the first failed read until the next good one; only after that can a new notice be sent.
    """

    def __init__(self, notifier: Notifier) -> None:
        """Keep the notifier; no incident is open."""
        self._notifier = notifier
        self._open = False

    async def incident(self, in_use: TimePolicy, reason: str) -> None:
        """Send the notice unless this incident already had one. A failed send is retried by the next failed read."""
        if self._open:
            return
        self._open = True  # before the await: two reads failing at once send one notice
        try:
            await self._notifier.say(notice_text(in_use, reason))
        except Exception as error:  # a Telegram fault must not stop the agent from alerting
            self._open = False
            logger.warning("policy_notice_failed error=%s", type(error).__name__)

    def recovered(self) -> None:
        """A good read ends the incident: the next failure gets its own notice."""
        self._open = False
