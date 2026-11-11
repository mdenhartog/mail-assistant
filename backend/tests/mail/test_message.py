from datetime import UTC, datetime, timedelta

import pytest

from app.mail.message import build_message

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _body(minutes: int = 10) -> str:
    message = build_message(
        "sender@example.test", "marco@example.test", "424242", NOW + timedelta(minutes=minutes), NOW
    )
    return message.get_content()


def test_body_has_code_and_validity_and_no_link() -> None:
    message = build_message("sender@example.test", "marco@example.test", "424242", NOW + timedelta(minutes=10), NOW)
    body = message.get_content()
    assert "424242" in body
    assert "valid for 10 minutes" in body
    assert "http" not in body.lower()
    assert "<a" not in body.lower()
    assert "://" not in body
    assert message.get_content_type() == "text/plain"


def test_subject_does_not_contain_the_code() -> None:
    message = build_message("sender@example.test", "marco@example.test", "424242", NOW + timedelta(minutes=10), NOW)
    assert "424242" not in str(message["Subject"])
    assert message["Subject"]


def test_headers_name_sender_and_recipient() -> None:
    message = build_message("sender@example.test", "marco@example.test", "424242", NOW + timedelta(minutes=10), NOW)
    assert message["From"] == "sender@example.test"
    assert message["To"] == "marco@example.test"


def test_validity_rounds_up_to_whole_minutes_and_is_singular_for_one() -> None:
    assert "valid for 1 minute." in _body(1)
    assert (
        "valid for 6 minutes"
        in build_message("a@b.test", "c@d.test", "1", NOW + timedelta(seconds=301), NOW).get_content()
    )


def test_expired_validity_is_refused() -> None:
    with pytest.raises(ValueError, match="expiry"):
        build_message("a@b.test", "c@d.test", "1", NOW, NOW)


def test_naive_datetimes_are_refused() -> None:
    with pytest.raises(ValueError, match="aware"):
        build_message("a@b.test", "c@d.test", "1", datetime(2026, 1, 1, 12, 10), NOW)  # noqa: DTZ001
