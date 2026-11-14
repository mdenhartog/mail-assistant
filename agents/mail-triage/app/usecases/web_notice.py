"""Tell Marco in Telegram about every change made on the web (spec C-8, AC-13; ADR-0033).

At each run the agent looks for web changes above the cursor, oldest version first, and for each one:

1. records the notice's own Undo token (never the conversation row, so a Telegram dialogue is not replaced),
2. sends the notice, then
3. moves the cursor past that change.

A failure anywhere stops the run with the cursor where it was, so the change is announced again on the next run:
delivery is at least once. The token is recorded before the send so a tap never finds a notice without its record; a
failed send leaves an unused record that expires. Quiet hours never hold a notice, so no policy is read here. Nothing
here reads the clock or makes a random value (they are injected) and nothing here logs: a zone or a token never
reaches a log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final, Protocol

from app.core import settings_text

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from app.core.alert_text import AlertMessage
    from schedule_policy.policy import TimePolicy

NOTICE_TTL: Final = timedelta(hours=24)  # as long as the Undo of a Telegram change (UNDO_TTL)


@dataclass(frozen=True, slots=True)
class WebChange:
    """One web change from the audit record: the version it made, when, and the values before and after."""

    version: int
    at: datetime
    old: TimePolicy | None  # ``None`` for the first saved row
    new: TimePolicy


@dataclass(frozen=True, slots=True)
class NoticeToken:
    """The own Undo token of one notice: the announced version, the values Undo restores and the burst it is in."""

    token: str
    version: int
    before: dict[str, object]
    created_at: datetime
    expires_at: datetime
    burst_id: str  # the same for every notice of one burst; never derived from ``before``
    first_version: int  # the first change of the burst


@dataclass(frozen=True, slots=True)
class OpenBurst:
    """A burst that was recorded but not fully announced: its id, first version and the values Undo restores."""

    burst_id: str
    first_version: int
    before: dict[str, object]


class NoticeStore(Protocol):
    """The audit records, the cursor and the token records."""

    async def last_announced(self) -> int:
        """The version of the last announced web change (0 when none)."""
        ...

    async def pending_after(self, version: int) -> list[WebChange]:
        """Web changes above ``version``, lowest version first."""
        ...

    async def open_burst(self, after: int, now: datetime) -> OpenBurst | None:
        """The burst of the lowest unexpired token record above version ``after``; ``None`` when there is none."""
        ...

    async def record_token(self, token: NoticeToken) -> None:
        """Store the token of a notice."""
        ...

    async def advance(self, version: int) -> None:
        """Move the cursor to ``version``; it never moves back."""
        ...


class NoticeChat(Protocol):
    """Telegram, sending a message with buttons."""

    async def send(self, message: AlertMessage) -> int:
        """Send it; return the Telegram message id."""
        ...


def _values(policy: TimePolicy | None) -> dict[str, object]:
    """The values as the store keeps them (minutes after midnight), ``{}`` when there was no row before."""
    if policy is None:
        return {}
    minutes = {
        "quiet_start": policy.quiet_start,
        "quiet_end": policy.quiet_end,
        "overview_at": policy.overview_at,
        "remind_at": policy.remind_at,
    }
    return {"zone": policy.zone, **{name: value.hour * 60 + value.minute for name, value in minutes.items()}}


class WebNotice:
    """Announces web changes."""

    def __init__(self, store: NoticeStore, chat: NoticeChat, new_token: Callable[[], str]) -> None:
        """Wire the store, Telegram and the token source."""
        self._store = store
        self._chat = chat
        self._new_token = new_token

    async def run(self, now: datetime) -> None:
        """Send one notice per web change not yet announced, in version order; stop at the first failure.

        All token records are written before the first send. A run that stopped half way left records above the
        cursor; the next run joins that burst, so Undo on the first notice still restores the values from before it.
        """
        cursor = await self._store.last_announced()
        pending = await self._store.pending_after(cursor)
        if not pending:
            return
        burst = await self._store.open_burst(cursor, now) or OpenBurst(
            self._new_token(), pending[0].version, _values(pending[0].old)
        )
        notices = [(change, self._new_token()) for change in pending]
        for change, token in notices:
            record = NoticeToken(
                token, change.version, burst.before, now, now + NOTICE_TTL, burst.burst_id, burst.first_version
            )
            await self._store.record_token(record)
        for change, token in notices:
            await self._chat.send(settings_text.web_notice(change.version, change.at, change.old, change.new, token))
            await self._store.advance(change.version)
