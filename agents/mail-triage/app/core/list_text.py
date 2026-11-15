"""The words of a category list notice (spec C-11, AC-29, AC-31, AC-48; ADR-0033, ADR-0046).

Names and descriptions are the user's own text but may carry markup or control characters (a stolen web session writes
them). Everything is sent as escaped plain text: no tag is written here, so nothing in a name can make a link or a
button. Control and format characters (also the bidirectional ones) become spaces, each piece is capped before it is
escaped (a cut never lands inside an entity), and whole lines are dropped, never cut, so the message stays within
Telegram's limit. A notice holds list data only: it never takes a sender or a subject. Nothing here logs.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from app.core.alert_text import MAX_MESSAGE_CHARS, AlertMessage, Button

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

UNDO: Final = "catundo"
LOCK: Final = "catlock"
UNDO_LABEL: Final = "Undo"
LOCK_LABEL: Final = "Undo and lock web sign-in"
DESCRIPTION_CHARS: Final = 60  # a notice shows the start of a description, the page shows the rest
NAME_CHARS: Final = 40  # category-policy NAME_MAX
_HEADER_RESERVE: Final = 400  # the header, two titles and the "and N more" lines
_UNSAFE: Final = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_NONCE: Final = re.compile(r"[A-Za-z0-9_-]{22,40}")  # 7 + 1 + 40 stays under Telegram's 64 bytes of callback data

NOTHING_TO_UNDO: Final = "There is nothing to undo. Nothing was changed."
CHANGED_SINCE: Final = "The list changed since then, so I did not undo anything. Nothing was changed."
ALREADY_DONE: Final = "Already done. Nothing was changed."
EXPIRED: Final = "Expired. Nothing was changed."
OTHER_CHAT: Final = "A button from another chat was ignored. Nothing was changed."
_LOCK_NOTE: Final = "Web sign-in is locked. Send /web_unlock to allow it again."


@dataclass(frozen=True, slots=True)
class ListCategory:
    """One category as a notice shows it."""

    id: str
    name: str
    description: str


def plain(value: str, cap: int) -> str:
    """One line of text: control and format characters and line breaks become spaces, cut at ``cap``, escaped."""
    cleaned = "".join(" " if unicodedata.category(char) in _UNSAFE else char for char in value)
    return html.escape(" ".join(cleaned.split())[:cap].strip(), quote=False)


def _line(category: ListCategory) -> str:
    name = plain(category.name, NAME_CHARS)
    description = plain(category.description, DESCRIPTION_CHARS)
    return f"- {name}: {description}" if description else f"- {name}"


def _section(title: str, categories: Sequence[ListCategory], budget: int) -> str:
    """The title and as many whole lines as fit in ``budget`` characters, then how many were left out."""
    if not categories:
        return f"{title}\n(no categories)"
    lines: list[str] = []
    used = 0
    for category in categories:
        line = _line(category)
        if used + len(line) + 1 > budget:
            break
        lines.append(line)
        used += len(line) + 1
    left_out = len(categories) - len(lines)
    if left_out:
        lines.append(f"...and {left_out} more")
    return "\n".join([title, *lines])


def button_data(action: str, nonce: str) -> str:
    """``<action>:<nonce>``; refuses what the Telegram callback data could not carry."""
    if action not in {UNDO, LOCK} or not _NONCE.fullmatch(nonce):
        raise ValueError("not a valid list button")
    return f"{action}:{nonce}"


def split_button(data: str) -> tuple[str, str] | None:
    """The action and the nonce of a list button, or ``None`` when ``data`` is not one."""
    action, _, nonce = data.partition(":")
    if action not in {UNDO, LOCK} or not _NONCE.fullmatch(nonce):
        return None
    return action, nonce


def change_notice(  # noqa: PLR0913 - one notice is made of these facts
    old: Sequence[ListCategory],
    new: Sequence[ListCategory],
    *,
    changes: int,
    at: datetime,
    undo_data: str,
    lock_data: str,
) -> AlertMessage:
    """The notice of a burst of list changes: old and new list, and the two buttons."""
    count = f"{changes} change{'s' if changes != 1 else ''}"
    header = f"Your category list was changed ({count}, last at {at:%Y-%m-%d %H:%M} UTC)."
    budget = (MAX_MESSAGE_CHARS - len(header) - _HEADER_RESERVE) // 2
    text = "\n\n".join([header, _section("Before:", old, budget), _section("Now:", new, budget)])
    return AlertMessage(text, (Button(UNDO_LABEL, undo_data), Button(LOCK_LABEL, lock_data)))


def undone(restored: Sequence[ListCategory], *, locked: bool = False) -> str:
    """The answer to a successful Undo: the list that is back, and the lock note when the lock button was used."""
    section = _section("Undone. The list from before is back:", restored, (MAX_MESSAGE_CHARS - _HEADER_RESERVE) // 2)
    return f"{section}\n\n{_LOCK_NOTE}" if locked else section


def locked(outcome: str) -> str:
    """An outcome with the note that web sign-in is locked."""
    return f"{outcome} {_LOCK_NOTE}"
