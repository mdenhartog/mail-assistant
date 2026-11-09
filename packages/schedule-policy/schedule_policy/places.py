"""Time-zone lookup over a hand-curated place list (spec C-6, ADR-0028).

Pure and offline: the list is the bundled ``places.json``; the UTC offset is computed for an injected ``now``.
"""

from __future__ import annotations

import difflib
import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from importlib import resources
from zoneinfo import ZoneInfo


MAX_TEXT_LENGTH = 64


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
    """Hits (at most 5), or a near-miss suggestion, or nothing."""

    hits: tuple[PlaceHit, ...] = ()
    suggestion: str | None = None



@dataclass(frozen=True)
class _Entry:
    name: str
    country: str
    zone: str


@dataclass(frozen=True)
class _Index:
    names: dict[str, tuple[_Entry, ...]]
    zones: dict[str, _Entry]


_LETTER_FOLDS = str.maketrans({"ı": "i", "ø": "o", "ł": "l", "đ": "d", "æ": "ae", "œ": "oe", "ð": "d", "þ": "th"})
_SUGGESTION_CUTOFF = 0.8


def _normalize(text: str) -> str:
    """Fold a name to a comparable key: width, case, accents, Turkish dotless i and spacing."""
    widened = unicodedata.normalize("NFKC", text).casefold().translate(_LETTER_FOLDS)
    bare = "".join(ch for ch in unicodedata.normalize("NFD", widened) if not unicodedata.combining(ch))
    return " ".join(bare.replace("-", " ").split())


@cache
def _index() -> _Index:
    data = json.loads(resources.files("schedule_policy").joinpath("places.json").read_text(encoding="utf-8"))
    names: dict[str, list[_Entry]] = {}
    zones: dict[str, _Entry] = {}
    for raw in data["places"]:
        entry = _Entry(raw["name"], raw["country"], raw["zone"])
        zones.setdefault(entry.zone.casefold(), entry)
        for key in (raw["name"], *raw["aliases"]):
            names.setdefault(_normalize(key), []).append(entry)
    return _Index({key: tuple(entries) for key, entries in names.items()}, zones)


def _format_offset(minutes: int) -> str:
    sign = "+" if minutes >= 0 else "-"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours}" + (f":{rest:02d}" if rest else "")


def _hit(entry: _Entry, now: datetime) -> PlaceHit:
    offset = now.astimezone(ZoneInfo(entry.zone)).utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset is not None else 0
    return PlaceHit(entry.zone, f"{entry.name}, {entry.country} ({_format_offset(minutes)})", minutes)


def lookup(text: str, *, now: datetime) -> LookupResult:
    """Find time zones for a typed place name; ``now`` must be timezone-aware."""
    if len(text) > MAX_TEXT_LENGTH:
        raise PlaceTextTooLongError(f"place text is longer than {MAX_TEXT_LENGTH} characters")
    index = _index()
    key = _normalize(text)
    if key in index.names:
        return LookupResult(hits=tuple(_hit(entry, now) for entry in index.names[key]))
    listed = index.zones.get(text.strip().casefold())
    if listed is not None:
        return LookupResult(hits=(_hit(listed, now),))
    close = difflib.get_close_matches(key, index.names, n=1, cutoff=_SUGGESTION_CUTOFF)
    if close:
        return LookupResult(suggestion=index.names[close[0]][0].name)
    return LookupResult()
