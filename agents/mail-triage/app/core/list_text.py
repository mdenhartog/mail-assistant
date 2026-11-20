"""The words of a category list notice (spec C-11, AC-29, AC-31, AC-48; ADR-0033, ADR-0046).

Names and descriptions are the user's own text but may carry markup or control characters (a stolen web session writes
them). Everything is sent as escaped plain text: no tag is written here, so nothing in a name can make a link or a
button. Control and format characters (also the bidirectional ones) become spaces, each piece is capped before it is
escaped (a cut never lands inside an entity), and whole lines are dropped, never cut, so the message stays within
Telegram's limit. A change notice shows every added, removed, renamed or re-described category first, with the old and
the new text; unchanged categories come after as a summary. When the changes do not fit, the notice says so.
A notice holds list data only: it never takes a sender or a subject. Nothing here logs.
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
DESCRIPTION_CHARS: Final = 60  # a restored list shows the start of a description
CHANGED_DESCRIPTION_CHARS: Final = 500  # category-policy DESCRIPTION_MAX: a changed category is shown in full
NAME_CHARS: Final = 40  # category-policy NAME_MAX
_HEADER_RESERVE: Final = 400  # the header, the titles and the closing lines
_UNSAFE: Final = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_NONCE: Final = re.compile(r"[A-Za-z0-9_-]{22,40}")  # 7 + 1 + 40 stays under Telegram's 64 bytes of callback data

NOTHING_TO_UNDO: Final = "There is nothing to undo. Nothing was changed."
CHANGED_SINCE: Final = "The list changed since then, so I did not undo anything. Nothing was changed."
ALREADY_DONE: Final = "Already done. Nothing was changed."
EXPIRED: Final = "Expired. Nothing was changed."
OTHER_CHAT: Final = "A button from another chat was ignored. Nothing was changed."
UNDO_NOTE: Final = "Undo restores the list. Mail already filed stays where it is."
_NOT_FIT: Final = "The changes do not fit in one message: {shown} of {total} are shown. Open the web page for the rest."
_TIERS: Final = (CHANGED_DESCRIPTION_CHARS, 200, 80, 0)  # the longest description cap at which all changes fit
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


def _text(value: str, cap: int) -> str:
    return plain(value, cap) or "(no description)"


def _changed_entries(old: Sequence[ListCategory], new: Sequence[ListCategory], cap: int) -> list[str]:
    """One entry per added, renamed, re-described or removed category; the new list's order, removed ones last."""
    before = {category.id: category for category in old}
    after = {category.id: category for category in new}
    entries: list[str] = []
    for category in new:
        was = before.get(category.id)
        name = plain(category.name, NAME_CHARS)
        if was is None:
            entries.append(f"+ Added: {name}: {_text(category.description, cap)}" if cap else f"+ Added: {name}")
        elif (was.name, was.description) != (category.name, category.description):
            entries.append(_changed_entry(was, category, cap))
    entries.extend(
        f"- Removed: {plain(c.name, NAME_CHARS)}: {_text(c.description, cap)}"
        if cap
        else f"- Removed: {plain(c.name, NAME_CHARS)}"
        for c in old
        if c.id not in after
    )
    return entries


def _changed_entry(was: ListCategory, now: ListCategory, cap: int) -> str:
    old_name, new_name = plain(was.name, NAME_CHARS), plain(now.name, NAME_CHARS)
    renamed = was.name != now.name
    head = f"~ Renamed: {old_name} -> {new_name}" if renamed else f"~ Changed: {new_name}"
    if was.description == now.description:
        return head
    old_text, new_text = _text(was.description, cap), _text(now.description, cap)
    if not cap or old_text == new_text:  # too little room to show the difference
        return f"{head}\n  The description changed."
    return f"{head}\n  Before: {old_text}\n  Now: {new_text}"


def _unchanged(old: Sequence[ListCategory], new: Sequence[ListCategory], room: int) -> str:
    """The unchanged categories: their names when they fit in ``room``, otherwise only how many."""
    before = {category.id: category for category in old}
    same = [
        c for c in new if c.id in before and (before[c.id].name, before[c.id].description) == (c.name, c.description)
    ]
    if not same:
        return ""
    names = ", ".join(plain(c.name, NAME_CHARS) for c in same)
    line = f"Unchanged ({len(same)}): {names}"
    return line if len(line) <= room else f"Unchanged ({len(same)}): not listed here"


def _changes_block(old: Sequence[ListCategory], new: Sequence[ListCategory], budget: int) -> str:
    """Every change with the most text that lets all of them fit; else as many whole entries as fit, and it says so."""
    for cap in _TIERS:
        entries = _changed_entries(old, new, cap)
        if sum(len(e) + 2 for e in entries) <= budget:
            return "\n\n".join(entries)
    entries = _changed_entries(old, new, 0)
    shown: list[str] = []
    used = len(_NOT_FIT.format(shown=len(entries), total=len(entries)))
    for entry in entries:
        if used + len(entry) + 2 > budget:
            break
        shown.append(entry)
        used += len(entry) + 2
    return "\n\n".join([*shown, _NOT_FIT.format(shown=len(shown), total=len(entries))])


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
    """The notice of a burst of list changes: what changed first, the rest summarised, and the two buttons."""
    count = f"{changes} change{'s' if changes != 1 else ''}"
    header = f"Your category list was changed ({count}, last at {at:%Y-%m-%d %H:%M} UTC)."
    budget = MAX_MESSAGE_CHARS - len(header) - len(UNDO_NOTE) - _HEADER_RESERVE
    block = _changes_block(old, new, budget)
    if not block:
        block = "No category was added, removed or changed; only the order differs."
    unchanged = _unchanged(old, new, budget - len(block))
    empty = ["The list is now empty (no categories)."] if not new else []
    parts = [header, block, *([unchanged] if unchanged else []), *empty, UNDO_NOTE]
    return AlertMessage("\n\n".join(parts), (Button(UNDO_LABEL, undo_data), Button(LOCK_LABEL, lock_data)))


def undone(restored: Sequence[ListCategory], *, locked: bool = False) -> str:
    """The answer to a successful Undo: the list that is back, and the lock note when the lock button was used."""
    section = _section("Undone. The list from before is back:", restored, (MAX_MESSAGE_CHARS - _HEADER_RESERVE) // 2)
    return f"{section}\n\n{_LOCK_NOTE}" if locked else section


def locked(outcome: str) -> str:
    """An outcome with the note that web sign-in is locked."""
    return f"{outcome} {_LOCK_NOTE}"
