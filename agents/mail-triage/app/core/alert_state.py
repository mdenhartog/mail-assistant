"""State of one alert (spec D5, D13; design "Alert state machine").

Pure logic: no clock, no I/O. A closed alert never returns to open, and an open alert has no transition that alerts a
second time on its own (AC-5); the only way back to ``OPEN`` is Marco's own choice (remind me later, cancel a draft).
"""

from __future__ import annotations

from enum import StrEnum


class AlertState(StrEnum):
    """Where an alert is in its life."""

    HELD = "held"  # urgent, but inside quiet hours: not sent yet
    OPEN = "open"  # sent to Marco, waiting for his choice
    SNOOZED = "snoozed"  # Marco asked to be reminded later
    DRAFTING = "drafting"  # Marco is writing a reply
    CONFIRMING = "confirming"  # the draft is shown, waiting for Send, Edit or Cancel
    CLOSED = "closed"  # finished: replied, or no more reminders


class Event(StrEnum):
    """What can happen to an alert."""

    QUIET_END = "quiet_end"
    REMIND_LATER = "remind_later"
    CLOSE = "close"
    START_DRAFT = "start_draft"
    SHOW_DRAFT = "show_draft"
    CANCEL_DRAFT = "cancel_draft"
    SENT = "sent"
    DUE = "due"
    DUE_IN_QUIET_HOURS = "due_in_quiet_hours"


class InvalidTransitionError(ValueError):
    """The event does not fit the state the alert is in."""


_TRANSITIONS: dict[tuple[AlertState, Event], AlertState] = {
    (AlertState.HELD, Event.QUIET_END): AlertState.OPEN,
    (AlertState.OPEN, Event.REMIND_LATER): AlertState.SNOOZED,
    (AlertState.OPEN, Event.CLOSE): AlertState.CLOSED,
    (AlertState.OPEN, Event.START_DRAFT): AlertState.DRAFTING,
    (AlertState.SNOOZED, Event.DUE): AlertState.OPEN,
    (AlertState.SNOOZED, Event.DUE_IN_QUIET_HOURS): AlertState.HELD,
    (AlertState.SNOOZED, Event.CLOSE): AlertState.CLOSED,
    (AlertState.DRAFTING, Event.SHOW_DRAFT): AlertState.CONFIRMING,
    (AlertState.DRAFTING, Event.CANCEL_DRAFT): AlertState.OPEN,
    (AlertState.CONFIRMING, Event.START_DRAFT): AlertState.DRAFTING,  # Edit
    (AlertState.CONFIRMING, Event.CANCEL_DRAFT): AlertState.OPEN,
    (AlertState.CONFIRMING, Event.SENT): AlertState.CLOSED,
}


def initial_state(*, in_quiet_hours: bool) -> AlertState:
    """State of the alert for a new urgent mail."""
    return AlertState.HELD if in_quiet_hours else AlertState.OPEN


def transition(state: AlertState, event: Event) -> AlertState:
    """Return the next state, or raise ``InvalidTransitionError`` when the event does not fit."""
    try:
        return _TRANSITIONS[(state, event)]
    except KeyError:
        raise InvalidTransitionError(f"{event} is not allowed while the alert is {state}") from None
