"""The buttons of a web notice and the unlock command (spec C-8, AC-13, AC-27; ADR-0033).

``webundo:<token>`` puts back the values as they were before the first web change of the burst the notice belongs to
(the token record holds them). The restore is an ordinary audited write guarded by a version: the highest version of
that burst, so a change that came later (Telegram, or a newer web change) makes it refuse and write nothing.
``weblock:<token>`` first sets ``web_auth.web_lock`` (setting it again changes nothing), then does the same undo, so
the lock holds even when the undo conflicts. ``/web_unlock`` deletes the lock row.

A token is used once: its record is deleted after the answer. A token past its life answers "Expired" and writes
nothing; one that is gone (used, or never made) answers "Already done". Nothing here touches the conversation row, so a
Telegram dialogue in progress is never replaced. Only the one allowed chat is served (the Telegram intake has already
checked the sender and that the chat is private); anything else is dropped without an answer. Nothing here reads the
clock or makes a random value (they are injected) and nothing logs: a zone, a token or a value never reaches a log.
"""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Final, Protocol

from app.core import settings_text
from app.db.repos import PolicyRefused, VersionConflict
from schedule_policy.policy import TimePolicy

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from datetime import datetime

    from app.adapters.telegram_inbox import Command
    from app.db.repos import StoredSettings
    from app.usecases.web_notice import NoticeToken

VIA: Final = "telegram"  # the channel recorded for an Undo, as for the Undo of a Telegram change
_MINUTE_COLUMNS: Final = ("quiet_start", "quiet_end", "overview_at", "remind_at")


class TokenStore(Protocol):
    """The token records of the notices."""

    async def find(self, token: str) -> NoticeToken | None:
        """The record of ``token``, expired or not; ``None`` when there is none (never made, or used)."""
        ...

    async def burst_end(self, before: dict[str, object]) -> int:
        """The highest announced version among the tokens that restore the same ``before``."""
        ...

    async def consume(self, token: str) -> bool:
        """Delete the record of ``token``; ``True`` when this call deleted it."""
        ...


class LockStore(Protocol):
    """``web_auth.web_lock``."""

    async def lock(self, now: datetime) -> None:
        """Set the lock; setting it again changes nothing."""
        ...

    async def unlock(self) -> bool:
        """Delete the lock row; ``True`` when there was one."""
        ...


class SettingsWriter(Protocol):
    """The settings store, as far as an Undo needs it."""

    async def write(self, policy: TimePolicy, expected_version: int, via: str, by: str) -> StoredSettings:
        """Replace the row if it is still at ``expected_version``."""
        ...


class ChatPort(Protocol):
    """Telegram."""

    async def say(self, text: str) -> None:
        """A short plain note."""
        ...

    async def edit_message(self, message_id: int, text: str) -> None:
        """Replace a message's text and remove its buttons."""
        ...


def _clock(minutes: object) -> time:
    if not isinstance(minutes, int) or isinstance(minutes, bool):
        raise ValueError("stored minutes are not a number")
    return time(minutes // 60, minutes % 60)


def _policy_before(before: Mapping[str, object]) -> TimePolicy | None:
    """The policy a token record restores; ``None`` when it holds nothing usable (a first row replaced nothing)."""
    zone = before.get("zone")
    if not isinstance(zone, str):
        return None
    try:
        quiet_start, quiet_end, overview_at, remind_at = (_clock(before.get(name)) for name in _MINUTE_COLUMNS)
    except ValueError:
        return None
    return TimePolicy(zone, quiet_start, quiet_end, overview_at, remind_at)


class WebNoticeActions:
    """Handles ``webundo``, ``weblock`` and ``/web_unlock``."""

    def __init__(  # noqa: PLR0913 - every dependency is injected for tests
        self,
        tokens: TokenStore,
        lock: LockStore,
        settings: SettingsWriter,
        chat: ChatPort,
        *,
        chat_id: int,
        by: str,
        now: Callable[[], datetime],
    ) -> None:
        """Wire the stores, Telegram, the one allowed chat, the actor text of an Undo and the clock."""
        self._tokens = tokens
        self._lock = lock
        self._settings = settings
        self._chat = chat
        self._chat_id = chat_id
        self._by = by
        self._now = now

    async def on_button(self, command: Command, action: str, token: str) -> None:
        """Run ``webundo`` or ``weblock`` for ``token``; answer by editing the notice, which drops its buttons."""
        if command.chat_id != self._chat_id:
            return
        record = await self._tokens.find(token)
        now = self._now()
        if record is None:
            await self._chat.edit_message(command.message_id, settings_text.WEB_DONE)
            return
        if record.expires_at <= now:
            await self._chat.edit_message(command.message_id, settings_text.WEB_EXPIRED)
            return
        locking = action == settings_text.WEB_LOCK
        if locking:
            await self._lock.lock(now)  # first: the lock must hold even when the undo cannot be done
        outcome = await self._undo(record)
        await self._tokens.consume(token)
        await self._chat.edit_message(command.message_id, settings_text.web_locked(outcome) if locking else outcome)

    async def _undo(self, record: NoticeToken) -> str:
        """Put the values from before the burst back, if the row is still at the end of the burst; say what happened."""
        policy = _policy_before(record.before)
        if policy is None:
            return settings_text.UNDO_REFUSED if record.before else settings_text.NOTHING_TO_UNDO
        guard = max(record.version, await self._tokens.burst_end(record.before))
        try:
            await self._settings.write(policy, guard, VIA, self._by)
        except VersionConflict:
            return settings_text.UNDO_CHANGED
        except PolicyRefused:
            return settings_text.UNDO_REFUSED
        return settings_text.WEB_UNDONE

    async def unlock(self, command: Command) -> None:
        """Lift the lock of web sign-in and say whether there was one; another chat gets no answer at all."""
        if command.chat_id != self._chat_id:
            return
        was_locked = await self._lock.unlock()
        await self._chat.say(settings_text.WEB_UNLOCKED if was_locked else settings_text.WEB_NOT_LOCKED)
