"""U-web-settings-26 (AC-13, W-11): the words of a web notice and its two buttons."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from app.core import settings_text
from schedule_policy.policy import TimePolicy

TOKEN = "AbCdEfGhIjKlMnOpQrStUv"  # noqa: S105  # 22 characters, like a 16-byte URL-safe token
OLD = TimePolicy("Europe/Amsterdam", time(23, 0), time(7, 0), time(18, 0), time(9, 0))
NEW = TimePolicy("Europe/Amsterdam", time(22, 0), time(7, 0), time(18, 0), time(9, 0))
AT = datetime(2026, 11, 11, 13, 5, tzinfo=UTC)  # 14:05 in Amsterdam


def test_given_a_changed_value_when_the_notice_is_built_then_it_shows_old_new_number_channel_and_time() -> None:
    message = settings_text.web_notice(3, AT, OLD, NEW, TOKEN)

    assert "change 3" in message.text
    assert "Channel: web" in message.text
    assert "2026-11-11 14:05 (Europe/Amsterdam)" in message.text
    assert "Quiet hours: 22:00 to 07:00 (was 23:00 to 07:00)" in message.text
    assert "Daily overview: 18:00 (unchanged)" in message.text


def test_given_a_notice_when_built_then_it_has_exactly_the_undo_and_the_undo_and_lock_buttons() -> None:
    message = settings_text.web_notice(3, AT, OLD, NEW, TOKEN)

    assert [(button.label, button.data) for button in message.buttons] == [
        ("Undo", f"webundo:{TOKEN}"),
        ("Undo and lock web sign-in", f"weblock:{TOKEN}"),
    ]


def test_given_no_earlier_row_when_the_notice_is_built_then_it_says_these_are_the_first_saved_values() -> None:
    message = settings_text.web_notice(1, AT, None, NEW, TOKEN)

    assert "first saved" in message.text
    assert "was" not in message.text


@pytest.mark.parametrize("token", ["", "short", "a" * 60, "has space" + "x" * 13, "é" * 22])
def test_given_a_token_that_does_not_fit_a_button_when_the_notice_is_built_then_it_is_refused(token: str) -> None:
    with pytest.raises(ValueError, match="token"):
        settings_text.web_notice(3, AT, OLD, NEW, token)
