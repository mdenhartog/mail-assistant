"""Time-zone lookup over a hand-curated place list (spec C-6, ADR-0028).

Pure and offline: the list is the bundled ``places.json``; the UTC offset is computed for an injected ``now``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from importlib import resources
from zoneinfo import ZoneInfo


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


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


@cache
def _index() -> dict[str, tuple[_Entry, ...]]:
    data = json.loads(resources.files("schedule_policy").joinpath("places.json").read_text(encoding="utf-8"))
    index: dict[str, list[_Entry]] = {}
    for raw in data["places"]:
        entry = _Entry(raw["name"], raw["country"], raw["zone"])
        for key in (raw["name"], *raw["aliases"]):
            index.setdefault(_normalize(key), []).append(entry)
    return {key: tuple(entries) for key, entries in index.items()}


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
    entries = _index().get(_normalize(text), ())
    return LookupResult(hits=tuple(_hit(entry, now) for entry in entries))
