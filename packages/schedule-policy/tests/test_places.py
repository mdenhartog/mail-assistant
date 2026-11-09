"""U-quiet-hours-02: place list and lookup (spec C-6, AC-9, AC-14 to AC-19, ADR-0028)."""

from __future__ import annotations

import json
import zoneinfo
from datetime import UTC, datetime
from importlib import resources

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


@pytest.mark.parametrize("text", ["Paris", "Sydney", "Georgia"])
def test_given_an_ambiguous_name_when_looked_up_then_at_most_5_labelled_hits(text):
    hits = places.lookup(text, now=NOW).hits

    assert 2 <= len(hits) <= 5
    assert all(hit.label.endswith(")") and ", " in hit.label and "(UTC" in hit.label for hit in hits)
    assert len({hit.zone for hit in hits}) == len(hits)


def test_given_paris_when_looked_up_then_france_comes_first():
    assert zones("Paris")[0] == "Europe/Paris"
    assert "America/Chicago" in zones("Paris")


def test_given_georgia_when_looked_up_then_both_the_country_and_the_us_state_are_offered():
    hits = {hit.zone: hit.label for hit in places.lookup("Georgia", now=NOW).hits}

    assert hits["Asia/Tbilisi"] == "Tbilisi, Georgia (UTC+4)"
    assert hits["America/New_York"] == "Georgia, United States (UTC-5)"


@pytest.mark.parametrize("text", ["USA", "usa", "United States", "U.S.A.", "US"])
def test_given_the_usa_when_looked_up_then_zones_with_city_names_capped_at_5(text):
    hits = places.lookup(text, now=NOW).hits

    assert len(hits) == 5
    assert [hit.zone for hit in hits[:3]] == ["America/New_York", "America/Chicago", "America/Denver"]
    assert hits[0].label == "New York, United States (UTC-5)"
    assert not any(hit.label.startswith("United States,") for hit in hits)


def test_given_australia_when_looked_up_then_zones_with_city_names():
    hits = places.lookup("Australia", now=SUMMER).hits

    assert {hit.zone for hit in hits} >= {"Australia/Sydney", "Australia/Perth", "Australia/Adelaide"}
    assert "Sydney, Australia (UTC+10)" in [hit.label for hit in hits]
    assert "Adelaide, Australia (UTC+9:30)" in [hit.label for hit in hits]


def test_given_a_one_zone_country_when_looked_up_then_one_city_named_hit():
    hits = places.lookup("Netherlands", now=NOW).hits

    assert [hit.label for hit in hits] == ["Amsterdam, Netherlands (UTC+1)"]


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


def test_given_punctuation_in_a_name_when_looked_up_then_it_is_ignored():
    assert zones("St. John's") == ["America/St_Johns"]
    assert zones("st johns") == ["America/St_Johns"]
    assert zones("Stratford-upon-Avon") == []


# --- the list itself (ADR-0028): guard tests -------------------------------------------------------------------


def _raw() -> dict[str, list[dict[str, object]]]:
    text = resources.files("schedule_policy").joinpath("places.json").read_text(encoding="utf-8")
    return json.loads(text)


def _all_zones() -> list[str]:
    data = _raw()
    zone_names = [str(p["zone"]) for p in data["places"]]
    for country in data["countries"]:
        zone_names.extend(str(z["zone"]) for z in country["zones"])  # type: ignore[attr-defined]
    return zone_names


def test_given_the_list_when_checked_against_tzdata_then_every_zone_exists():
    available = zoneinfo.available_timezones()

    assert [z for z in _all_zones() if z not in available] == []
    for zone in set(_all_zones()):
        zoneinfo.ZoneInfo(zone)


def test_given_the_list_when_checked_then_every_entry_has_a_label():
    data = _raw()
    for place in data["places"]:
        assert str(place["name"]).strip(), place
        assert str(place["country"]).strip(), place
        assert isinstance(place["aliases"], list)
    for country in data["countries"]:
        assert str(country["name"]).strip(), country
        assert country["zones"], country
        for zone in country["zones"]:  # type: ignore[attr-defined]
            assert str(zone["city"]).strip(), country

    for zone in set(_all_zones()):
        assert places.lookup(zone, now=NOW).hits[0].label.strip(), zone


def test_given_the_list_when_counted_then_it_has_all_countries_and_a_few_hundred_cities():
    data = _raw()

    assert len(data["countries"]) >= 193
    assert 300 <= len(data["places"]) <= 700


def test_given_every_country_name_when_looked_up_then_it_has_between_1_and_5_hits():
    for country in _raw()["countries"]:
        hits = places.lookup(str(country["name"]), now=NOW).hits
        assert 1 <= len(hits) <= 5, country["name"]


def test_given_every_place_name_when_looked_up_then_it_is_found_with_its_zone():
    for place in _raw()["places"]:
        found = [hit.zone for hit in places.lookup(str(place["name"]), now=NOW).hits]
        assert place["zone"] in found or len(found) == 5, place["name"]


def test_given_every_entry_when_looked_up_across_a_year_then_labels_never_fail():
    for zone in set(_all_zones()):
        for month in range(1, 13):
            moment = datetime(2026, month, 15, 12, 0, tzinfo=UTC)
            assert places.lookup(zone, now=moment).hits[0].utc_offset_minutes % 15 == 0


def test_given_a_naive_now_when_looked_up_then_an_error():
    with pytest.raises(ValueError, match="timezone"):
        places.lookup("New York", now=datetime(2026, 1, 15, 12, 0))  # noqa: DTZ001
