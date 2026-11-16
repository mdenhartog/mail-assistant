"""The words of the approval notice, case by case (AC-42, AC-48; mutation gate, U-mail-categories-34)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core import approval_text

AT = datetime(2026, 11, 14, 9, 5, tzinfo=UTC)
NONCE = "A" * 22
TAIL = "(at 09:05 UTC). Only labels change. Cancel the move before then to stop it, or lock web sign-in."


def _notice(count: int, seconds: int) -> approval_text.AlertMessage:
    return approval_text.scheduled_notice(
        count, AT, now=AT - timedelta(seconds=seconds), cancel_data="c", lock_data="l"
    )


@pytest.mark.parametrize(
    ("count", "seconds", "head"),
    [
        (1, 900, "1 mail moves in 15 minutes"),
        (2, 900, "2 mails move in 15 minutes"),
        (0, 900, "0 mails move in 15 minutes"),
        (3, 60, "3 mails move in 1 minute"),
        (3, 61, "3 mails move in 2 minutes"),
        (3, 120, "3 mails move in 2 minutes"),
        (3, 1, "3 mails move in 1 minute"),
        (3, 0, "3 mails move in 1 minute"),
        (3, -500, "3 mails move in 1 minute"),
    ],
)
def test_given_a_count_and_a_wait_when_announced_then_the_words_and_minutes_are_exact(
    count: int, seconds: int, head: str
) -> None:
    message = _notice(count, seconds)
    assert message.text == f"{head} {TAIL}"
    assert [(b.label, b.data) for b in message.buttons] == [
        ("Cancel the move", "c"),
        ("Stop it and lock web sign-in", "l"),
    ]


def test_given_the_notice_when_arguments_are_positional_then_they_are_refused() -> None:
    with pytest.raises(TypeError):
        approval_text.scheduled_notice(1, AT, AT, "c", "l")  # type: ignore[misc]


@pytest.mark.parametrize(
    ("plans", "text"),
    [(0, "No waiting plan was stopped."), (1, "1 plan stopped."), (2, "2 plans stopped."), (5, "5 plans stopped.")],
)
def test_given_a_number_of_stopped_plans_when_locked_then_the_answer_counts_them(plans: int, text: str) -> None:
    assert (
        approval_text.locked_and_cancelled(plans)
        == f"{text} Web sign-in is locked. Send /web_unlock to allow it again."
    )


def test_given_button_parts_when_checked_then_only_a_valid_action_and_nonce_pass() -> None:
    for action in ("plancancel", "planlock", "planback"):
        assert approval_text.button_data(action, NONCE) == f"{action}:{NONCE}"
        assert approval_text.split_button(f"{action}:{NONCE}") == (action, NONCE)
    for action, nonce in (("other", NONCE), ("plancancel", "short"), ("other", "short")):
        with pytest.raises(ValueError, match="not a valid plan button"):
            approval_text.button_data(action, nonce)
    for data in (f"other:{NONCE}", "plancancel:short", "other:short", "plancancel"):
        assert approval_text.split_button(data) is None
