"""Pure rules of the security events (U-web-settings-13)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.auth import event_rules

KINDS = {
    "code_refused": "refused",
    "code_invalid": "refused",
    "code_request_refused": "refused",
    "mail_failed": "failed",
    "session_start": "ok",
    "session_end": "ok",
    "csrf_refused": "refused",
    "rate_limited": "refused",
    "lock_refused": "refused",
}
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(("kind", "result"), KINDS.items())
def test_each_kind_has_its_result(kind: str, result: str) -> None:
    assert event_rules.result_for(kind) == result


@pytest.mark.parametrize("kind", ["", "CODE_REFUSED", "code_refused ", "login", "drop table"])
def test_an_unknown_kind_is_refused(kind: str) -> None:
    with pytest.raises(event_rules.UnknownEventKindError):
        event_rules.result_for(kind)


def test_window_is_the_floor_of_epoch_minutes() -> None:
    base = event_rules.event_window(T0)
    assert base == int(T0.timestamp()) // 60
    assert event_rules.event_window(T0 + timedelta(seconds=59, milliseconds=900)) == base
    assert event_rules.event_window(T0 + timedelta(seconds=60)) == base + 1


def test_window_floors_instead_of_truncating_before_the_epoch() -> None:
    assert event_rules.event_window(datetime(1969, 12, 31, 23, 59, 30, tzinfo=UTC)) == -1


@pytest.mark.parametrize(
    ("client", "expected"),
    [
        ("203.0.113.7", "ipv4"),
        ("2001:db8::1", "ipv6"),
        ("2001:db8::/64", "ipv6"),
        ("2001:db8:1:2::/64", "ipv6"),
        ("203.0.113.0/24", "ipv4"),
        ("2001:db8::/129", "other"),
        ("203.0.113.7/33", "other"),
        ("/64", "other"),
        ("not-an-address", "other"),
        ("", "other"),
        ("203.0.113.7.9", "other"),
    ],
)
def test_client_class_names_the_family_only(client: str, expected: str) -> None:
    assert event_rules.client_class(client) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a" * 32, True),
        ("0" * 64, True),
        ("a" * 31, False),
        ("a" * 33, False),
        ("A" * 32, False),
        ("g" * 32, False),
        ("canary-user", False),
        ("", False),
        ("a" * 32 + "\n", False),
    ],
)
def test_username_hash_shape(value: str, expected: bool) -> None:
    assert event_rules.valid_username_hash(value) is expected


@pytest.mark.parametrize("kind", ["code_refused"])
def test_a_repeat_of_a_counted_kind_is_counted(kind: str) -> None:
    assert event_rules.counts_repeats(kind) is True


@pytest.mark.parametrize(
    "kind",
    [k for k in KINDS if k != "code_refused"],
)
def test_a_repeat_of_any_other_kind_is_dropped_so_a_flood_writes_one_row_a_window(kind: str) -> None:
    assert event_rules.counts_repeats(kind) is False


def test_an_unknown_kind_has_no_repeat_rule() -> None:
    with pytest.raises(event_rules.UnknownEventKindError):
        event_rules.counts_repeats("login")
