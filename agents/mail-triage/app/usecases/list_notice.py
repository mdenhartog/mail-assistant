"""Tell the user in Telegram about every change of the category list, and undo it (spec C-11, D17, AC-31, AC-48).

See ADR-0033 and ADR-0046.

At each run the agent reads the audit of list versions above the notice cursor. The versions the agent wrote itself
(channel ``telegram``: the seed and an Undo, which the database derives from the login, never from the writer) are
skipped. Everything else found in one run is one burst and gets exactly one notice: the list from before the burst, the
list now, and two buttons, "Undo" and "Undo and lock web sign-in". Quiet hours never hold it, so no policy is read.

Each button carries a single-use nonce (``telegram_actions``) whose target is ``<first>-<last>``: the first version
of the burst and the latest version when it was announced. Undo writes the list from before the first version as a new
version, only while the latest version is still ``<last>``; a later change makes it refuse and write nothing. The
lock button sets the web lock first, so the lock holds even when the Undo is refused. The answer is an edit of the
notice, which drops its buttons; the agent's own Undo makes no further notice (the next run skips it).

Delivery is at least once: the cursor moves after the send, so a failed send announces the burst again with new
nonces (an unused one only expires). Nothing here reads the clock or makes a random value (both are injected), nothing
logs, and a notice holds list data only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from app.core import list_text
from app.usecases.telegram_actions import Refusal

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from app.adapters.telegram_inbox import Command
    from app.core.alert_text import AlertMessage
    from app.core.list_text import ListCategory
    from app.usecases.telegram_actions import Redeemed, TelegramActions

OWN_CHANNEL: Final = "telegram"  # list versions written by the agent's own login
FIRST_VERSION: Final = 1


class ListChanged(Exception):  # noqa: N818 - a plain fact, not an error condition of the program
    """The list is no longer at the version the Undo was made for."""


@dataclass(frozen=True, slots=True)
class ListChange:
    """One audit record of the list: the version made, when, by which channel, and the list before and after."""

    version: int
    at: datetime
    channel: str
    old: tuple[ListCategory, ...]
    new: tuple[ListCategory, ...]


class ListNoticeStore(Protocol):
    """The list audit, the notice cursor and the write of a restored list."""

    async def last_announced(self) -> int:
        """The version up to which changes were announced (0 when none)."""
        ...

    async def pending_after(self, version: int) -> list[ListChange]:
        """Audit records above ``version``, lowest version first."""
        ...

    async def change(self, version: int) -> ListChange | None:
        """The audit record of ``version``."""
        ...

    async def advance(self, version: int) -> None:
        """Move the notice cursor to ``version``; it never moves back."""
        ...

    async def restore(self, categories: Sequence[ListCategory], expected_version: int) -> int:
        """Write ``categories`` as a new version if the latest version is ``expected_version``; return the new one.

        Raises ``ListChanged`` otherwise. Channel and actor of the version are the database's, never the caller's.
        """
        ...


class NoticeChat(Protocol):
    """Telegram."""

    async def send(self, message: AlertMessage) -> int:
        """Send it; return the Telegram message id."""
        ...

    async def say(self, text: str) -> None:
        """A short plain note."""
        ...

    async def edit_message(self, message_id: int, text: str) -> None:
        """Replace a message's text and remove its buttons."""
        ...


class WebLock(Protocol):
    """``web_auth.web_lock``."""

    async def lock(self, now: datetime) -> bool:
        """Set the lock; ``True`` when this call set it."""
        ...


class ListNotice:
    """Announces list changes."""

    def __init__(self, store: ListNoticeStore, chat: NoticeChat, actions: TelegramActions, *, chat_id: int) -> None:
        """Wire the store, Telegram, the button nonces and the one allowed chat."""
        self._store = store
        self._chat = chat
        self._actions = actions
        self._chat_id = chat_id

    async def run(self, now: datetime) -> None:
        """Send one notice for everything not yet announced, then move the cursor past it."""
        pending = await self._store.pending_after(await self._store.last_announced())
        if not pending:
            return
        latest = pending[-1].version
        burst = [change for change in pending if change.channel != OWN_CHANNEL]
        if burst:
            target = f"{burst[0].version}-{latest}"
            undo = await self._actions.issue("undo", target, self._chat_id, now)
            lock = await self._actions.issue("lock", target, self._chat_id, now)
            message = list_text.change_notice(
                burst[0].old,
                pending[-1].new,
                changes=len(burst),
                at=burst[-1].at,
                undo_data=list_text.button_data(list_text.UNDO, undo),
                lock_data=list_text.button_data(list_text.LOCK, lock),
            )
            await self._chat.send(message)
        await self._store.advance(latest)


class ListNoticeActions:
    """Handles ``catundo`` and ``catlock``."""

    def __init__(  # noqa: PLR0913 - every dependency is injected for tests
        self,
        actions: TelegramActions,
        store: ListNoticeStore,
        lock: WebLock,
        chat: NoticeChat,
        *,
        chat_id: int,
        now: Callable[[], datetime],
    ) -> None:
        """Wire the nonces, the list store, the web lock, Telegram, the one allowed chat and the clock."""
        self._actions = actions
        self._store = store
        self._lock = lock
        self._chat = chat
        self._chat_id = chat_id
        self._now = now

    async def on_button(self, command: Command, action: str, nonce: str) -> None:
        """Run ``catundo`` or ``catlock``; the answer replaces the notice, which drops its buttons."""
        if command.chat_id != self._chat_id:  # never edit by message id for a chat that is not ours
            await self._chat.say(list_text.OTHER_CHAT)
            return
        locking = action == list_text.LOCK
        now = self._now()
        outcome = await self._actions.redeem(nonce, "lock" if locking else "undo", command.chat_id, now)
        if isinstance(outcome, Refusal):
            await self._chat.edit_message(command.message_id, _REFUSALS[outcome])
            return
        if locking:
            await self._lock.lock(now)  # first: the lock must hold even when the Undo cannot be done
        answer = await self._undo(outcome)
        await self._chat.edit_message(command.message_id, list_text.locked(answer) if locking else answer)

    async def _undo(self, redeemed: Redeemed) -> str:
        """Put the list from before the burst back if it is still as the burst left it; say what happened."""
        first, last = _versions(redeemed.target)
        change = await self._store.change(first) if first > FIRST_VERSION else None
        if change is None:
            return list_text.NOTHING_TO_UNDO
        try:
            await self._store.restore(change.old, last)
        except ListChanged:
            return list_text.CHANGED_SINCE
        return list_text.undone(change.old)


_REFUSALS: Final = {
    Refusal.DONE: list_text.ALREADY_DONE,
    Refusal.EXPIRED: list_text.EXPIRED,
    Refusal.OTHER_CHAT: list_text.OTHER_CHAT,
}


def _versions(target: str) -> tuple[int, int]:
    """The first and last version of a burst from a button's target (written by this module only)."""
    first, _, last = target.partition("-")
    return int(first), int(last)
