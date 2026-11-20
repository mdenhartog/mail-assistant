"""The words and buttons of the delayed-apply notice and of the result notice (spec D16, D17, AC-42, AC-48; ADR-0046).

A notice holds counts and times only: it never takes a sender, a subject or a category name. The button data is
``<action>:<nonce>``; the nonce is single use (``telegram_actions``). Nothing here logs.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from app.core.alert_text import AlertMessage, Button

if TYPE_CHECKING:
    from datetime import datetime

CANCEL: Final = "plancancel"
LOCK: Final = "planlock"
MOVE_BACK: Final = "planback"
CANCEL_LABEL: Final = "Cancel the move"
LOCK_LABEL: Final = "Stop it and lock web sign-in"
MOVE_BACK_LABEL: Final = "Move back"
_ACTIONS: Final = frozenset({CANCEL, LOCK, MOVE_BACK})
_NONCE: Final = re.compile(r"[A-Za-z0-9_-]{22,40}")  # 10 + 1 + 40 stays under Telegram's 64 bytes of callback data

CANCELLED: Final = "Cancelled. Nothing was moved."
TOO_LATE: Final = (
    "Too late to cancel: the waiting time is over, so the move has started or is done. Nothing was cancelled."
)
NOT_WAITING: Final = "This approval is no longer waiting. Nothing was changed."
ALREADY_DONE: Final = "Already done. Nothing was changed."
EXPIRED: Final = "Expired. Nothing was changed."
OTHER_CHAT: Final = "A button from another chat was ignored. Nothing was changed."
MOVE_BACK_ASKED: Final = "Move back requested. I will tell you when it is done."
MOVE_BACK_UNAVAILABLE: Final = (
    "There is nothing to move back for this plan (not applied, or already asked). Nothing was changed."
)
_LOCK_NOTE: Final = "Web sign-in is locked. Send /web_unlock to allow it again."


def button_data(action: str, nonce: str) -> str:
    """``<action>:<nonce>``; refuses what the Telegram callback data could not carry."""
    if action not in _ACTIONS or not _NONCE.fullmatch(nonce):
        raise ValueError("not a valid plan button")
    return f"{action}:{nonce}"


def split_button(data: str) -> tuple[str, str] | None:
    """The action and the nonce of a plan button, or ``None`` when ``data`` is not one."""
    action, _, nonce = data.partition(":")
    if action not in _ACTIONS or not _NONCE.fullmatch(nonce):
        return None
    return action, nonce


def scheduled_notice(count: int, at: datetime, *, now: datetime, cancel_data: str, lock_data: str) -> AlertMessage:
    """'N mails move in M minutes (at HH:MM UTC)' with Cancel the move and Stop it and lock.

    The zone is stated because the user's own time zone is not stored here.
    """
    what = f"{count} mail moves" if count == 1 else f"{count} mails move"
    minutes = max(1, -(-int((at - now).total_seconds()) // 60))
    unit = "minute" if minutes == 1 else "minutes"
    text = (
        f"{what} in {minutes} {unit} (at {at:%H:%M} UTC). Only labels change. "
        "Cancel the move before then to stop it, or lock web sign-in."
    )
    return AlertMessage(text, (Button(CANCEL_LABEL, cancel_data), Button(LOCK_LABEL, lock_data)))


def locked_and_cancelled(plans: int) -> str:
    """The answer to Lock: how many waiting or running plans were stopped, and the lock note."""
    stopped = "No waiting plan was stopped." if plans == 0 else f"{plans} plan{'s' if plans != 1 else ''} stopped."
    return f"{stopped} {_LOCK_NOTE}"
