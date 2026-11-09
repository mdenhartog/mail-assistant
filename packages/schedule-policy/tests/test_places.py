"""U-quiet-hours-02: place list and lookup (spec C-6, AC-9, AC-14 to AC-19, ADR-0028)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from schedule_policy import places

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)  # winter: no daylight saving in the northern hemisphere
SUMMER = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def zones(text: str, now: datetime = NOW) -> list[str]:
    return [hit.zone for hit in places.lookup(text, now=now).hits]


@pytest.mark.parametrize("text", ["New York", "new york", "NEW YORK", "nEw yOrK", "new  york"])
def test_given_new_york_in_any_case_when_looked_up_then_america_new_york(text):
    assert zones(text) == ["America/New_York"]


def test_given_new_york_when_looked_up_then_hit_has_label_and_offset_at_now():
    winter = places.lookup("New York", now=NOW).hits[0]
    summer = places.lookup("New York", now=SUMMER).hits[0]

    assert winter.label == "New York, United States (UTC-5)"
    assert winter.utc_offset_minutes == -300
    assert summer.label == "New York, United States (UTC-4)"
    assert summer.utc_offset_minutes == -240
