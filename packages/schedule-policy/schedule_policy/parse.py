"""Typed clock times (spec C-3): a strict reader that gives a ``time`` or ``None``, never an exception.

Accepted: ``7``, ``7:00``, ``07:00``, ``0700``, ``19.30``, ``7am``, ``7:30pm`` (one optional space before am/pm,
spaces around the text). ``00:00`` and ``24:00`` both mean midnight. Everything else is refused: seconds, full-width
or other non-ASCII digits, control characters, empty text and text over 64 characters.
"""

from __future__ import annotations

import re
from datetime import time

MAX_TEXT_LENGTH = 64
_SEPARATED = re.compile(r"([0-9]{1,2})(?:[:.]([0-9]{2}))?(?: ?(am|pm))?", re.ASCII | re.IGNORECASE)
_COMPACT = re.compile(r"([0-9]{2})([0-9]{2})", re.ASCII)
_LAST_HOUR = 23
_MIDNIGHT_HOUR = 24
_LAST_MINUTE = 59
_NOON = 12


def _twelve_hour(hour: int, meridiem: str) -> int | None:
    if not 1 <= hour <= _NOON:
        return None
    return hour % _NOON + (_NOON if meridiem.lower() == "pm" else 0)


def _clock(hour: int, minute: int) -> time | None:
    if minute > _LAST_MINUTE:
        return None
    if hour == _MIDNIGHT_HOUR:
        return time(0, 0) if minute == 0 else None
    return time(hour, minute) if hour <= _LAST_HOUR else None


def parse_time(text: str) -> time | None:
    """Read a typed clock time; ``None`` if the text is not one of the accepted forms."""
    if len(text) > MAX_TEXT_LENGTH:
        return None
    body = text.strip(" ")
    compact = _COMPACT.fullmatch(body)
    if compact:
        return _clock(int(compact[1]), int(compact[2]))
    match = _SEPARATED.fullmatch(body)
    if match is None:
        return None
    hour, minute = int(match[1]), int(match[2] or 0)
    if match[3] is None:
        return _clock(hour, minute)
    twelve = _twelve_hour(hour, match[3])
    return None if twelve is None else _clock(twelve, minute)
