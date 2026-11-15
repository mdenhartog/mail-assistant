"""The Telegram side of the apply: plain notes and the result notice with its two buttons (INT-004, ADR-0046 point 7).

``Move back`` and ``Lock web sign-in`` each carry a single-use nonce of their own (``telegram_actions``): only its hash
is stored in ``telegram_action`` with the chat, the kind (``move_back`` or ``lock``) and the plan as target. The
callback data is ``planback:<nonce>`` or ``planlock:<nonce>``. Pressing a button is handled elsewhere (U-mail-categories-16),
which redeems the nonce for the same kind and acts on its target. The notice text holds numbers and the names of labels
only (D18); it is escaped here because Telegram shows it as HTML.
"""

from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING, Final

from app.core.alert_text import AlertMessage, Button
from app.usecases.resort_apply import Offer

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable
    from datetime import datetime

    from app.usecases.list_notice import NoticeChat
    from app.usecases.telegram_actions import TelegramActions

__all__ = ["LOCK_ACTION", "MOVE_BACK_ACTION", "TelegramApplyNotifier", "split_button"]

MOVE_BACK_ACTION: Final = "planback"
LOCK_ACTION: Final = "planlock"
_NONCE: Final = re.compile(r"[A-Za-z0-9_-]{22,40}")  # as the list buttons: the data stays under Telegram's 64 bytes
_BUTTONS: Final = {
    Offer.MOVE_BACK: ("move_back", MOVE_BACK_ACTION, "Move back"),
    Offer.LOCK: ("lock", LOCK_ACTION, "Lock web sign-in"),
}


def split_button(data: str) -> tuple[str, str] | None:
    """The action and the nonce of a result-notice button, or ``None`` when ``data`` is not one."""
    action, _, nonce = data.partition(":")
    if action not in {MOVE_BACK_ACTION, LOCK_ACTION} or not _NONCE.fullmatch(nonce):
        return None
    return action, nonce


class TelegramApplyNotifier:
    """``ApplyNotifier`` (and ``BuildNotifier``) on the Telegram chat and the nonce store."""

    def __init__(
        self, chat: NoticeChat, actions: TelegramActions, *, chat_id: int, now: Callable[[], datetime]
    ) -> None:
        """Wire the chat, the nonces, the one allowed chat and the clock."""
        self._chat = chat
        self._actions = actions
        self._chat_id = chat_id
        self._now = now

    async def say(self, text: str) -> None:
        """Send a plain note."""
        await self._chat.say(text)

    async def result(self, text: str, *, plan_id: uuid.UUID, offers: tuple[Offer, ...]) -> None:
        """Send the result notice; every offer becomes a button with its own nonce for this plan."""
        buttons: list[Button] = []
        for offer in offers:
            kind, action, label = _BUTTONS[offer]
            nonce = await self._actions.issue(kind, str(plan_id), self._chat_id, self._now())
            buttons.append(Button(label, f"{action}:{nonce}"))
        await self._chat.send(AlertMessage(html.escape(text, quote=False), tuple(buttons)))
