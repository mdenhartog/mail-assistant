"""Time-zone lookup over a hand-curated place list (spec C-6, ADR-0028).

Pure and offline: the list is the bundled ``places.json``; the UTC offset is computed for an injected ``now``.
"""

from __future__ import annotations

import difflib
import json
import unicodedata
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from datetime import datetime

MAX_TEXT_LENGTH = 64
MAX_HITS = 5


class PlaceTextTooLongError(ValueError):
    """The typed text is longer than ``MAX_TEXT_LENGTH`` characters; it is refused before any matching."""


@dataclass(frozen=True)
class PlaceHit:
    """One selectable time zone: its IANA name, a button label and the UTC offset at lookup time."""

    zone: str
    label: str
    utc_offset_minutes: int


@dataclass(frozen=True)
class LookupResult:
    """Hits (at most ``MAX_HITS``), or a near-miss suggestion, or nothing."""

    hits: tuple[PlaceHit, ...] = ()
    suggestion: str | None = None


@dataclass(frozen=True)
class _Entry:
    """A selectable zone, named after a city: ``name, country``."""

    name: str
    country: str
    zone: str


@dataclass(frozen=True)
class _Index:
    names: dict[str, tuple[_Entry, ...]]  # normalised name or alias -> entries, in file order
    display: dict[str, str]  # normalised name or alias -> the name shown in "Did you mean ...?"
    zones: dict[str, _Entry]  # lower-case IANA name -> the entry that labels it


# Letters that Unicode decomposition does not split into base letter + accent: dotless i, o-slash, l-stroke,
# d-stroke, ae and oe ligatures, eth, thorn. Written as escapes so that the source is unambiguous.
_LETTER_FOLDS = str.maketrans(
    {
        "ı": "i",  # noqa: RUF001 - dotless i is the point of this table
        "ø": "o",
        "ł": "l",
        "đ": "d",
        "æ": "ae",
        "œ": "oe",
        "ð": "d",
        "þ": "th",
    }
)
_DROPPED = str.maketrans("", "", ".'`" + chr(0x2018) + chr(0x2019))  # full stop, apostrophes, typographic quotes
_SUGGESTION_CUTOFF = 0.8


def _normalize(text: str) -> str:
    """Fold a name to a comparable key: width, case, accents, Turkish dotless i, punctuation and spacing."""
    widened = unicodedata.normalize("NFKC", text).casefold().translate(_LETTER_FOLDS).translate(_DROPPED)
    bare = "".join(ch for ch in unicodedata.normalize("NFD", widened) if not unicodedata.combining(ch))
    return " ".join(bare.replace("-", " ").split())


def _load() -> dict[str, Any]:
    text = resources.files("schedule_policy").joinpath("places.json").read_text(encoding="utf-8")
    return json.loads(text)


@cache
def _index() -> _Index:
    data = _load()
    names: dict[str, list[_Entry]] = {}
    display: dict[str, str] = {}
    zones: dict[str, _Entry] = {}

    def add(name: str, aliases: list[str], entries: list[_Entry]) -> None:
        for key in (_normalize(name), *(_normalize(alias) for alias in aliases)):
            names.setdefault(key, []).extend(entries)
            display.setdefault(key, name)
        for entry in entries:
            zones.setdefault(entry.zone.casefold(), entry)

    for country in data["countries"]:
        add(
            country["name"],
            country["aliases"],
            [_Entry(z["city"], country["name"], z["zone"]) for z in country["zones"]],
        )
    for place in data["places"]:
        add(place["name"], place["aliases"], [_Entry(place["name"], place["country"], place["zone"])])
    return _Index({key: tuple(entries) for key, entries in names.items()}, display, zones)


def _format_offset(minutes: int) -> str:
    sign = "+" if minutes >= 0 else "-"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours}" + (f":{rest:02d}" if rest else "")


def _hit(entry: _Entry, now: datetime) -> PlaceHit:
    offset = now.astimezone(ZoneInfo(entry.zone)).utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    return PlaceHit(entry.zone, f"{entry.name}, {entry.country} ({_format_offset(minutes)})", minutes)


def _distinct_zones(entries: tuple[_Entry, ...]) -> list[_Entry]:
    """Keep the first entry per zone, so that two buttons never lead to the same zone."""
    seen: dict[str, _Entry] = {}
    for entry in entries:
        seen.setdefault(entry.zone, entry)
    return list(seen.values())


def lookup(text: str, *, now: datetime) -> LookupResult:
    """Find time zones for a typed place name; ``now`` must be timezone-aware.

    Raises:
        PlaceTextTooLongError: the text is longer than ``MAX_TEXT_LENGTH``; refused before matching.
        ValueError: ``now`` has no time zone.
    """
    if len(text) > MAX_TEXT_LENGTH:
        raise PlaceTextTooLongError(f"place text is longer than {MAX_TEXT_LENGTH} characters")
    if now.utcoffset() is None:
        raise ValueError("now must carry a timezone")
    index = _index()
    key = _normalize(text)
    if key in index.names:
        entries = _distinct_zones(index.names[key])[:MAX_HITS]
        return LookupResult(hits=tuple(_hit(entry, now) for entry in entries))
    listed = index.zones.get(text.strip().casefold())
    if listed is not None:
        return LookupResult(hits=(_hit(listed, now),))
    close = difflib.get_close_matches(key, index.names, n=1, cutoff=_SUGGESTION_CUTOFF)
    if close:
        return LookupResult(suggestion=index.display[close[0]])
    return LookupResult()
