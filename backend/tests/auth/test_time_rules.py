"""Boundary tests for the pure time rules of the sign-in code and the session (U-web-settings-11)."""

import ast
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.auth import code_rules, expiry

D = datetime(2026, 11, 10, tzinfo=UTC)


def at(h: int, m: int = 0, s: int = 0, us: int = 0) -> datetime:
    return D.replace(hour=h, minute=m, second=s, microsecond=us)


TTL = timedelta(seconds=600)
COOLDOWN = timedelta(seconds=60)


# Criterion 1: code life
@pytest.mark.parametrize(("now", "expected"), [(at(14, 9, 59), False), (at(14, 10), True), (at(14, 10, 1), True)])
def test_code_expired_boundary(now: datetime, expected: bool) -> None:
    assert code_rules.code_expired(at(14), now, TTL) is expected


def test_code_not_expired_before_creation_time_is_reached() -> None:
    assert code_rules.code_expired(at(14), at(13, 59), TTL) is False


# Criterion 2: attempts
@pytest.mark.parametrize(("attempts", "expected"), [(0, False), (4, False), (5, True), (6, True)])
def test_attempts_exhausted_boundary(attempts: int, expected: bool) -> None:
    assert code_rules.attempts_exhausted(attempts, 5) is expected


@pytest.mark.parametrize(("attempts", "expected"), [(0, (1, False)), (3, (4, False)), (4, (5, True))])
def test_register_wrong_fifth_attempt_kills_the_code(attempts: int, expected: tuple[int, bool]) -> None:
    assert code_rules.register_wrong(attempts, 5) == expected


def test_register_wrong_refuses_a_sixth_attempt_without_counting() -> None:
    with pytest.raises(ValueError, match="exhausted"):
        code_rules.register_wrong(5, 5)


# Criterion 3: cooldown over every request
@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (at(14), 60),
        (at(14, 0, 59), 1),
        (at(14, 0, 59, 500_000), 1),
        (at(14, 0, 30), 30),
        (at(14, 1), 0),
        (at(14, 1, 1), 0),
        (at(13, 59), 60),
    ],
)
def test_cooldown_remaining_boundary(now: datetime, expected: int) -> None:
    assert code_rules.cooldown_remaining(at(14), now, COOLDOWN) == expected


def test_cooldown_remaining_without_a_previous_request_is_zero() -> None:
    assert code_rules.cooldown_remaining(None, at(14), COOLDOWN) == 0


# Criterion 4: hourly cap over sent codes only
FIRST = at(13, 0, 1)


@pytest.mark.parametrize(("now", "expected"), [(at(14), True), (at(14, 0, 1), False), (at(14, 0, 2), False)])
def test_first_send_falls_out_of_the_hour(now: datetime, expected: bool) -> None:
    sent = [FIRST, at(13, 10), at(13, 20), at(13, 30), at(13, 40)]
    assert code_rules.hourly_cap_reached(sent, now, 5) is expected


def test_hourly_cap_not_reached_with_four_and_reached_with_five() -> None:
    four = [at(13, 10), at(13, 20), at(13, 30), at(13, 40)]
    assert code_rules.hourly_cap_reached(four, at(14), 5) is False
    assert code_rules.hourly_cap_reached([*four, at(13, 50)], at(14), 5) is True


def test_hourly_cap_ignores_old_sends_and_counts_more_than_the_cap() -> None:
    old = [at(9), at(10), at(11), at(12), at(12, 30)]
    assert code_rules.hourly_cap_reached(old, at(14), 5) is False
    assert code_rules.hourly_cap_reached([at(13, 30 + i) for i in range(6)], at(14), 5) is True


def test_hourly_cap_with_no_sends() -> None:
    assert code_rules.hourly_cap_reached([], at(14), 5) is False


# Criterion 5: idle expiry
@pytest.mark.parametrize(("now", "expected"), [(at(14, 29, 59), False), (at(14, 30), True), (at(14, 30, 1), True)])
def test_idle_expired_boundary(now: datetime, expected: bool) -> None:
    assert expiry.idle_expired(at(14), now) is expected


# Criterion 6: absolute expiry
@pytest.mark.parametrize(("now", "expected"), [(at(19, 59, 59), False), (at(20), True), (at(20, 0, 1), True)])
def test_absolute_expired_boundary(now: datetime, expected: bool) -> None:
    assert expiry.absolute_expired(at(8), now) is expected


def test_session_with_activity_every_twenty_minutes_ends_at_twelve_hours() -> None:
    created = at(8)
    seen = created
    now = created + timedelta(minutes=20)
    while now < at(19, 59, 59):
        assert expiry.idle_expired(seen, now) is False
        seen = now
        now += timedelta(minutes=20)
    assert expiry.idle_expired(seen, at(19, 59, 59)) is False
    assert expiry.absolute_expired(created, at(19, 59, 59)) is False
    assert expiry.absolute_expired(created, at(20)) is True


def test_next_idle_expiry_slides_by_thirty_minutes() -> None:
    assert expiry.next_idle_expiry(at(8, 20), at(8)) == at(8, 50)


def test_next_idle_expiry_is_capped_at_the_absolute_limit() -> None:
    assert expiry.next_idle_expiry(at(19, 50), at(8)) == at(20)
    assert expiry.next_idle_expiry(at(19, 29, 59), at(8)) == at(19, 59, 59)
    assert expiry.next_idle_expiry(at(19, 30), at(8)) == at(20)


# Criterion 7: naive datetimes are refused
NAIVE = datetime(2026, 11, 10, 14)  # noqa: DTZ001


@pytest.mark.parametrize(
    "call",
    [
        lambda: code_rules.code_expired(NAIVE, at(14), TTL),
        lambda: code_rules.code_expired(at(14), NAIVE, TTL),
        lambda: code_rules.cooldown_remaining(NAIVE, at(14), COOLDOWN),
        lambda: code_rules.cooldown_remaining(at(14), NAIVE, COOLDOWN),
        lambda: code_rules.hourly_cap_reached([NAIVE], at(14), 5),
        lambda: code_rules.hourly_cap_reached([], NAIVE, 5),
        lambda: expiry.idle_expired(NAIVE, at(14)),
        lambda: expiry.idle_expired(at(14), NAIVE),
        lambda: expiry.absolute_expired(NAIVE, at(14)),
        lambda: expiry.absolute_expired(at(14), NAIVE),
        lambda: expiry.next_idle_expiry(NAIVE, at(8)),
        lambda: expiry.next_idle_expiry(at(8), NAIVE),
    ],
)
def test_naive_datetimes_raise(call: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        call()


def test_other_time_zones_compare_by_instant() -> None:
    plus_two = timezone(timedelta(hours=2))
    assert code_rules.code_expired(at(14), at(16, 10).astimezone(plus_two), TTL) is True
    assert code_rules.code_expired(at(14), at(16, 9, 59).astimezone(plus_two), TTL) is False


# Criterion 8: standard library only, marker present
@pytest.mark.parametrize("name", ["code_rules", "expiry"])
def test_modules_import_only_the_standard_library(name: str) -> None:
    source = (Path(__file__).parents[2] / "app" / "auth" / f"{name}.py").read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= set(sys.stdlib_module_names)
    assert source.startswith("# pure module (mutation-gated)")
