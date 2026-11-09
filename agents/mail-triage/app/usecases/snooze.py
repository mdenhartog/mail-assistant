"""Snooze, close and release-when-due for alerts (spec AC-9, AC-10, AC-32).

Marco's answer to "remind me later" is free text, so it is parsed strictly: whole hours from 1 to 168, or the word
"tomorrow". Anything else keeps the alert as it is and asks again. A due alert is sent exactly once because it goes
back to ``open`` (or ``held`` in quiet hours) flagged for resending, and the delivery use case sends open alerts once.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, Protocol

from app.core.alert_state import AlertState, Event, InvalidTransitionError, transition
from app.core.time_policy import InvalidSnoozeError, in_quiet_hours, remind_due
from schedule_policy.policy import DEFAULT_POLICY

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

NOT_OPEN = "That alert is no longer open."
ASK_AGAIN = "Please send a whole number of hours (1 to 168) or the word 'tomorrow'."
_HOURS = re.compile(r"[0-9]{1,4}")


class SnoozeStore(Protocol):
    """Persistence for alert states."""

    async def state_of(self, alert_id: str) -> AlertState | None:
        """Current state, or ``None`` for an unknown alert."""
        ...

    async def set_state(
        self, alert_id: str, state: AlertState, *, due_at: datetime | None = None, resend: bool = False
    ) -> None:
        """Save the state; ``resend`` clears the stored Telegram message so the alert is sent again."""
        ...

    async def due_snoozed(self, now: datetime) -> list[str]:
        """Ids of snoozed alerts whose due time has passed."""
        ...

    async def record_audit(self, kind: str, alert_id: str) -> None:
        """Write an audit entry: kind and alert id only."""
        ...


class Say(Protocol):
    """Plain text to Marco in the Telegram chat."""

    async def say(self, text: str) -> None:
        """Send a short message."""
        ...


def _parse(text: str) -> int | Literal["tomorrow"] | None:
    cleaned = text.strip().casefold()
    if cleaned == "tomorrow":
        return "tomorrow"
    return int(cleaned) if _HOURS.fullmatch(cleaned) else None


class SnoozeService:
    """The snooze, close and release-when-due commands."""

    def __init__(self, store: SnoozeStore, say: Say, now: Callable[[], datetime]) -> None:
        """Wire the store, the chat and the clock."""
        self._store = store
        self._say = say
        self._now = now

    async def snooze(self, alert_id: str, answer: str) -> None:
        """Snooze an open alert for the hours (or "tomorrow") Marco typed."""
        if not await self._allowed(alert_id, Event.REMIND_LATER):
            return
        amount = _parse(answer)
        try:
            if amount is None:
                raise InvalidSnoozeError
            due = remind_due(self._now(), amount, DEFAULT_POLICY)
        except InvalidSnoozeError:
            await self._say.say(ASK_AGAIN)
            return
        await self._store.set_state(alert_id, AlertState.SNOOZED, due_at=due)
        await self._store.record_audit("alert_snoozed", alert_id)

    async def close(self, alert_id: str) -> None:
        """Close the alert for good ('no more reminders'); the mail keeps its category."""
        if not await self._allowed(alert_id, Event.CLOSE):
            return
        await self._store.set_state(alert_id, AlertState.CLOSED)
        await self._store.record_audit("alert_closed", alert_id)

    async def release_due(self) -> list[str]:
        """Reopen snoozed alerts that are due (held when it is quiet hours); each one only once."""
        now = self._now()
        event = Event.DUE_IN_QUIET_HOURS if in_quiet_hours(now, DEFAULT_POLICY) else Event.DUE
        released: list[str] = []
        for alert_id in await self._store.due_snoozed(now):
            await self._store.set_state(alert_id, transition(AlertState.SNOOZED, event), resend=True)
            released.append(alert_id)
        return released

    async def _allowed(self, alert_id: str, event: Event) -> bool:
        state = await self._store.state_of(alert_id)
        try:
            if state is None:
                raise InvalidTransitionError
            transition(state, event)
        except InvalidTransitionError:
            await self._say.say(NOT_OPEN)
            return False
        return True
