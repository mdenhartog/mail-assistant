"""U-02: the alert state machine (spec AC-5, AC-7, AC-8, AC-9, AC-10, AC-32)."""

from __future__ import annotations

import pytest

from app.core.alert_state import AlertState, Event, InvalidTransitionError, initial_state, transition

ALL_EVENTS = tuple(Event)


def test_given_an_urgent_mail_outside_quiet_hours_when_created_then_the_alert_is_open() -> None:
    assert initial_state(in_quiet_hours=False) is AlertState.OPEN


def test_given_an_urgent_mail_inside_quiet_hours_when_created_then_the_alert_is_held() -> None:
    assert initial_state(in_quiet_hours=True) is AlertState.HELD


def test_given_a_held_alert_when_quiet_hours_end_then_it_is_open() -> None:
    assert transition(AlertState.HELD, Event.QUIET_END) is AlertState.OPEN


def test_given_an_open_alert_when_closed_then_it_is_closed_and_never_returns_to_open() -> None:
    closed = transition(AlertState.OPEN, Event.CLOSE)

    assert closed is AlertState.CLOSED
    for event in ALL_EVENTS:
        with pytest.raises(InvalidTransitionError):
            transition(closed, event)


def test_given_an_open_alert_when_nothing_happens_then_no_transition_exists_to_alert_again() -> None:
    """AC-5: an open alert stays open; the only way to a second alert is the explicit snooze path."""
    for event in (Event.QUIET_END, Event.DUE, Event.DUE_IN_QUIET_HOURS, Event.SENT, Event.SHOW_DRAFT):
        with pytest.raises(InvalidTransitionError):
            transition(AlertState.OPEN, event)


def test_given_an_open_alert_when_remind_later_then_snoozed_and_when_due_then_open_once() -> None:
    snoozed = transition(AlertState.OPEN, Event.REMIND_LATER)
    reopened = transition(snoozed, Event.DUE)

    assert snoozed is AlertState.SNOOZED
    assert reopened is AlertState.OPEN
    with pytest.raises(InvalidTransitionError):
        transition(reopened, Event.DUE)


def test_given_a_snoozed_alert_that_is_due_inside_quiet_hours_when_released_then_it_is_held() -> None:
    assert transition(AlertState.SNOOZED, Event.DUE_IN_QUIET_HOURS) is AlertState.HELD


def test_given_a_snoozed_alert_when_marco_closes_it_then_it_is_closed() -> None:
    assert transition(AlertState.SNOOZED, Event.CLOSE) is AlertState.CLOSED


def test_given_a_draft_being_confirmed_when_cancelled_then_the_alert_is_open_again() -> None:
    assert transition(AlertState.CONFIRMING, Event.CANCEL_DRAFT) is AlertState.OPEN
    assert transition(AlertState.DRAFTING, Event.CANCEL_DRAFT) is AlertState.OPEN


def test_given_a_confirming_alert_when_sent_then_it_is_closed() -> None:
    assert transition(AlertState.CONFIRMING, Event.SENT) is AlertState.CLOSED


def test_given_an_open_alert_when_a_reply_is_typed_then_it_goes_through_drafting_and_confirming() -> None:
    drafting = transition(AlertState.OPEN, Event.START_DRAFT)
    confirming = transition(drafting, Event.SHOW_DRAFT)

    assert (drafting, confirming) == (AlertState.DRAFTING, AlertState.CONFIRMING)
    assert transition(confirming, Event.START_DRAFT) is AlertState.DRAFTING  # Edit


@pytest.mark.parametrize(
    ("state", "event"),
    [
        (AlertState.HELD, Event.CLOSE),
        (AlertState.HELD, Event.REMIND_LATER),
        (AlertState.OPEN, Event.SENT),
        (AlertState.SNOOZED, Event.START_DRAFT),
        (AlertState.DRAFTING, Event.SENT),
        (AlertState.CONFIRMING, Event.REMIND_LATER),
        (AlertState.CLOSED, Event.QUIET_END),
    ],
)
def test_given_an_event_that_does_not_fit_the_state_when_applied_then_it_is_refused(
    state: AlertState, event: Event
) -> None:
    with pytest.raises(InvalidTransitionError):
        transition(state, event)
