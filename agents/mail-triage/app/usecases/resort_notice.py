"""The Telegram side of the apply: plain notes and the result notice (INT-004, ADR-0046 point 7).

The buttons and their single-use nonces belong to ``ApprovalNotice`` (U-mail-categories-16): the result notice goes
through its ``send_result``. This adapter only escapes the text (Telegram shows it as HTML and it names a label) and
supplies the clock.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable
    from datetime import datetime

    from app.usecases.list_notice import NoticeChat
    from app.usecases.resort_apply import Offer

__all__ = ["ResultNotice", "TelegramApplyNotifier"]


class ResultNotice(Protocol):
    """What the notifier needs of ``ApprovalNotice``."""

    async def send_result(self, text: str, plan_id: uuid.UUID, offers: tuple[Offer, ...], now: datetime) -> int:
        """Send the result ``text`` with the buttons of ``offers``."""
        ...


class TelegramApplyNotifier:
    """``ApplyNotifier`` and ``BuildNotifier`` on the chat and the approval notice."""

    def __init__(self, chat: NoticeChat, notice: ResultNotice, *, now: Callable[[], datetime]) -> None:
        """Wire the chat, the approval notice and the clock."""
        self._chat = chat
        self._notice = notice
        self._now = now

    async def say(self, text: str) -> None:
        """Send a plain note."""
        await self._chat.say(text)

    async def result(self, text: str, *, plan_id: uuid.UUID, offers: tuple[Offer, ...]) -> None:
        """Send the result notice with a Move back and/or Lock button, each with its own nonce."""
        await self._notice.send_result(html.escape(text, quote=False), plan_id, offers, self._now())
