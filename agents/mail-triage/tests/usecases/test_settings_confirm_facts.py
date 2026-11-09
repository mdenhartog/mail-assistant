"""U-quiet-hours-11: the facts behind the confirmation, derived from an injected moment (no dialogue, no store)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from app.core.settings_text import ClockChange, city_of, offset_label
from app.usecases.settings_confirm import next_clock_change


def utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("minutes", "label"),
    [(-300, "UTC-5"), (60, "UTC+1"), (330, "UTC+5:30"), (345, "UTC+5:45"), (-210, "UTC-3:30"), (0, "UTC+0")],
)
def test_given_an_offset_in_minutes_when_labelled_then_whole_hours_are_short_and_part_hours_have_minutes(
    minutes: int, label: str
) -> None:
    assert offset_label(minutes) == label


@pytest.mark.parametrize(
    ("zone", "city"),
    [
        ("America/New_York", "New York"),
        ("Europe/Amsterdam", "Amsterdam"),
        ("America/Argentina/Buenos_Aires", "Buenos Aires"),
    ],
)
def test_given_a_zone_name_when_spoken_then_it_is_the_city_part(zone: str, city: str) -> None:
    assert city_of(zone) == city


@pytest.mark.parametrize(
    ("zone", "now", "expected"),
    [
        ("Australia/Lord_Howe", utc("2026-09-25T00:00"), ClockChange(date(2026, 10, 4), time(2, 0), 630, 660)),
        ("America/St_Johns", utc("2027-03-01T12:00"), ClockChange(date(2027, 3, 14), time(2, 0), -210, -150)),
        ("Europe/Amsterdam", utc("2026-10-20T12:00"), ClockChange(date(2026, 10, 25), time(3, 0), 120, 60)),
        ("Asia/Kolkata", utc("2026-10-20T12:00"), None),
        ("Europe/Amsterdam", utc("2026-11-09T12:00"), None),
    ],
)
def test_given_a_zone_and_a_moment_when_the_next_clock_change_is_asked_then_it_is_dated_within_14_days(
    zone: str, now: datetime, expected: ClockChange | None
) -> None:
    assert next_clock_change(now, zone) == expected
