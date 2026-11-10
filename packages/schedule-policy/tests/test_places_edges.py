"""U-quiet-hours-16g: edge cases of the place lookup that the mutation run showed to be unpinned."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from schedule_policy import places

WINTER = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
LONG_AGO = datetime(1900, 1, 1, 12, 0, tzinfo=UTC)  # before standard time: offsets with seconds (local mean time)


def _hit(text: str, zone: str, now: datetime) -> places.PlaceHit:
    return next(hit for hit in places.lookup(text, now=now).hits if hit.zone == zone)


def test_given_a_zone_on_utc_when_looked_up_then_the_offset_is_shown_with_a_plus_sign():
    hit = _hit("London", "Europe/London", WINTER)

    assert hit.utc_offset_minutes == 0
    assert hit.label == "London, United Kingdom (UTC+0)"


def test_given_a_local_mean_time_offset_with_seconds_when_looked_up_then_minutes_round_down():
    # Sao Paulo was UTC-3:06:28 in 1900: -11188 s is -187 minutes rounded down, not -186.
    hit = _hit("Sao Paulo", "America/Sao_Paulo", LONG_AGO)

    assert hit.utc_offset_minutes == -187
    assert hit.label == "Sao Paulo, Brazil (UTC-3:07)"


@pytest.mark.parametrize("quote", [chr(0x2018), chr(0x2019), "`", "'"])
def test_given_any_apostrophe_or_typographic_quote_when_looked_up_then_it_is_ignored(quote):
    hits = places.lookup(f"Cote d{quote}Ivoire", now=WINTER).hits

    assert [hit.zone for hit in hits] == ["Africa/Abidjan"]


def test_given_now_passed_by_position_when_looked_up_then_refused_because_it_is_keyword_only():
    lookup = places.lookup

    with pytest.raises(TypeError):
        lookup("Paris", WINTER)  # pyright: ignore[reportCallIssue]


def test_given_the_place_index_when_asked_twice_then_it_is_built_once():
    assert places._index() is places._index()


@pytest.mark.parametrize(
    "value",
    [
        places.PlaceHit("Europe/Paris", "Paris, France (UTC+1)", 60),
        places.LookupResult(suggestion="Paris"),
        next(iter(places._index().zones.values())),
        places._index(),
    ],
    ids=["hit", "result", "entry", "index"],
)
def test_given_a_lookup_value_when_a_field_is_assigned_then_it_is_refused_because_it_is_frozen(value):
    field = dataclasses.fields(value)[0].name

    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, field, None)
