"""U-mail-categories-07 criterion 4 (AC-29, MC-5): a list notice is escaped plain text within Telegram's limit."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime

from app.core import list_text
from app.core.alert_text import MAX_MESSAGE_CHARS
from app.core.list_text import ListCategory
from tests.fakes.seeds import BIDI_CONTROLS

AT = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
UNDO, LOCK = "catundo:AAAAAAAAAAAAAAAAAAAAAA", "catlock:BBBBBBBBBBBBBBBBBBBBBB"
BELL = chr(7)
NUL = chr(0)
ENTITY = re.compile(r"&(?!(?:amp|lt|gt);)")
TAG = re.compile(r"<[^>]*>")


def _notice(old: list[ListCategory], new: list[ListCategory], changes: int = 1) -> list_text.AlertMessage:
    return list_text.change_notice(tuple(old), tuple(new), changes=changes, at=AT, undo_data=UNDO, lock_data=LOCK)


def test_given_markup_and_control_characters_in_a_category_then_the_notice_is_escaped_plain_text() -> None:
    hostile = ListCategory("1", '<b>Bills</b> & "more"', f'<a href="http://evil.test">click</a>{NUL}{BELL}\nsecond line')
    bidi = ListCategory("2", f"Work{BIDI_CONTROLS[0]}gnp", f"x{BIDI_CONTROLS[1]}y")

    message = _notice([ListCategory("3", "Old", "")], [hostile, bidi])

    assert not TAG.search(message.text)  # no tag at all, so no hidden link and no fake button
    assert "&lt;b&gt;Bills&lt;/b&gt; &amp;" in message.text
    assert not ENTITY.search(message.text)
    forbidden = {"Cc", "Cf"}
    assert not [c for c in message.text if unicodedata.category(c) in forbidden and c != "\n"]


def test_given_the_biggest_possible_lists_then_the_notice_stays_within_the_message_limit() -> None:
    big = [ListCategory(str(n), "&" * 40, "<" * 500) for n in range(50)]

    message = _notice(big, list(reversed(big)))

    assert len(message.text) <= MAX_MESSAGE_CHARS
    assert not ENTITY.search(message.text)
    assert not TAG.search(message.text)
    assert "more" in message.text  # what did not fit is counted, not silently cut
    assert [button.label for button in message.buttons] == ["Undo", "Undo and lock web sign-in"]


def test_given_a_short_list_change_then_both_lists_are_shown_in_full_with_the_buttons() -> None:
    old = [ListCategory("1", "Bills", "Invoices"), ListCategory("2", "Travel", "")]
    new = [ListCategory("1", "Bills", "Invoices and receipts")]

    message = _notice(old, new, changes=2)

    for fact in ("2 changes", "Before", "Now", "Bills: Invoices", "Travel", "Bills: Invoices and receipts"):
        assert fact in message.text
    assert [button.data for button in message.buttons] == [UNDO, LOCK]


def test_given_an_empty_list_then_the_notice_says_so() -> None:
    message = _notice([ListCategory("1", "Bills", "")], [])

    assert "no categories" in message.text
