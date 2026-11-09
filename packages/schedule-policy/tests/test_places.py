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


def test_given_64_and_65_characters_when_looked_up_then_the_second_is_refused_before_matching(monkeypatch):
    assert places.lookup("a" * 64, now=NOW).hits == ()

    def fail_if_matching(*_args: object) -> None:
        raise AssertionError("matching must not run for a refused text")

    monkeypatch.setattr(places, "_index", fail_if_matching)
    with pytest.raises(places.PlaceTextTooLongError):
        places.lookup("a" * 65, now=NOW)


def test_given_new_york_when_looked_up_then_hit_has_label_and_offset_at_now():
    winter = places.lookup("New York", now=NOW).hits[0]
    summer = places.lookup("New York", now=SUMMER).hits[0]

    assert winter.label == "New York, United States (UTC-5)"
    assert winter.utc_offset_minutes == -300
    assert summer.label == "New York, United States (UTC-4)"
    assert summer.utc_offset_minutes == -240


@pytest.mark.parametrize(
    ("text", "suggestion"),
    [("Nwe York", "New York"), ("Viena", "Vienna"), ("Zuirch", "Zurich"), ("Istanbl", "Istanbul")],
)
def test_given_a_near_miss_when_looked_up_then_a_suggestion_and_no_hits(text, suggestion):
    result = places.lookup(text, now=NOW)

    assert result.hits == ()
    assert result.suggestion == suggestion


@pytest.mark.parametrize("text", ["", "   ", "xyzzy", "qqqqqqqq", "'; DROP TABLE x;--", "../etc", "12345"])
def test_given_text_matching_nothing_when_looked_up_then_an_empty_result(text):
    assert places.lookup(text, now=NOW) == places.LookupResult()


def test_given_a_listed_iana_name_when_looked_up_then_accepted():
    hits = places.lookup("Europe/Vienna", now=NOW).hits

    assert [hit.zone for hit in hits] == ["Europe/Vienna"]
    assert hits[0].label == "Vienna, Austria (UTC+1)"
    assert zones("europe/vienna") == ["Europe/Vienna"]


@pytest.mark.parametrize("text", ["Europe/Nowhere", "Antarctica/Troll", "UTC", "America/../etc"])
def test_given_an_unlisted_iana_name_when_looked_up_then_nothing(text):
    assert places.lookup(text, now=NOW) == places.LookupResult()


@pytest.mark.parametrize(
    ("text", "zone"),
    [
        ("NYC", "America/New_York"),
        ("nyc", "America/New_York"),
        ("Wien", "Europe/Vienna"),
        ("Den Haag", "Europe/Amsterdam"),
        ("  Zürich  ", "Europe/Zurich"),
        ("Zurich", "Europe/Zurich"),
    ],
)
def test_given_alias_or_surrounding_spaces_when_looked_up_then_matched(text, zone):
    assert zones(text) == [zone]


@pytest.mark.parametrize(
    ("text", "zone"),
    [
        ("Zürich", "Europe/Zurich"),  # NFD: u + combining diaeresis
        ("Zürich", "Europe/Zurich"),  # NFC
        ("ZÜRICH", "Europe/Zurich"),
        ("Ｎｅｗ Ｙｏｒｋ", "America/New_York"),  # full-width "New York"
        ("São Paulo", "America/Sao_Paulo"),
        ("Sao Paulo", "America/Sao_Paulo"),
        ("São Paulo", "America/Sao_Paulo"),  # NFD
        ("ıstanbul", "Europe/Istanbul"),  # dotless i
        ("İstanbul", "Europe/Istanbul"),  # dotted capital I
        ("ISTANBUL", "Europe/Istanbul"),
    ],
)
def test_given_unicode_variants_when_looked_up_then_each_matches(text, zone):
    assert zones(text) == [zone]
