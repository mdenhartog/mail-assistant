"""The confirmation after a successful settings write, and Undo (spec C-7, C-8; AC-20, AC-21; threat T-4).

After every write (a time zone, quiet hours, the overview or reminder time, the one-tap move, an Undo) Marco gets the
full picture: the zone with its UTC offset, the local time there and, when the zone changed, in the zone he left, the
quiet hours in both zones, the next overview and the next clock change within 14 days. Everything is derived from the
injected clock and the stored policy; nothing here reads the system clock.

The confirmation carries an Undo button. Its conversation (kind ``settings``, step ``undo``, the version just written)
lives 24 hours, long enough to survive 15 minutes and an agent restart; a newer dialogue replaces it. Undo asks
``SettingsStore.undo`` for exactly that version, so a row that changed since is never touched.

Nothing here logs: not a zone, not a nonce. Store failures reach the dialogue's guard, which logs class and SQLSTATE.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

from app.core import settings_text
from app.core.settings_text import ClockChange, Elsewhere, Picture
from app.core.time_policy import local_day, next_overview, next_quiet_end, next_quiet_start
from app.db.repos import NothingToUndo, PolicyRefused, StoredSettingsInvalid, VersionConflict
from app.usecases.dispatch import UNDO_STEP, button_data

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.db.pg_conversation import OpenConversation
    from app.db.repos import SettingsStore, StoredSettings
    from app.usecases.dispatch import ConversationPort
    from app.usecases.settings_dialog import DialogChat
    from schedule_policy.policy import TimePolicy

UNDO_TTL: Final = timedelta(hours=24)
CLOCK_CHANGE_DAYS: Final = 14
_ONE_HOUR = timedelta(hours=1)
_ONE_MINUTE = timedelta(minutes=1)


def _local(moment: datetime, zone: str) -> time:
    local = moment.astimezone(ZoneInfo(zone))
    return time(local.hour, local.minute)


def _offset(moment: datetime, zone: str) -> timedelta:
    return moment.astimezone(ZoneInfo(zone)).utcoffset() or timedelta(0)


def _minutes(offset: timedelta) -> int:
    return int(offset.total_seconds() // 60)


def next_clock_change(now: datetime, zone: str) -> ClockChange | None:
    """The first clock change after ``now``, up to and including 14 days ahead; ``None`` if the offset stays."""
    end = now + timedelta(days=CLOCK_CHANGE_DAYS)
    start = now
    while start < end:
        stop = min(start + _ONE_HOUR, end)
        if _offset(stop, zone) != _offset(start, zone):
            return _change_before(stop, zone)
        start = stop
    return None


def _change_before(stop: datetime, zone: str) -> ClockChange:
    """The change that happened in the hour that ends at ``stop`` (the first minute with the new offset)."""
    after = _offset(stop, zone)
    moment = stop
    while _offset(moment - _ONE_MINUTE, zone) == after:
        moment -= _ONE_MINUTE
    before = _offset(moment - _ONE_MINUTE, zone)
    wall = (moment + before).astimezone(UTC)  # the wall clock shown just before the change, read off as UTC
    return ClockChange(wall.date(), time(wall.hour, wall.minute), _minutes(before), _minutes(after))


def _day_word(moment: datetime, now: datetime, policy: TimePolicy) -> str:
    day = local_day(moment, policy)
    return {0: "today", 1: "tomorrow"}.get((day - local_day(now, policy)).days, day.isoformat())


def picture(headline: str, previous: TimePolicy | None, policy: TimePolicy, now: datetime) -> Picture:
    """What the confirmation says about ``policy`` at ``now``; ``previous`` is the policy it replaced, if any."""
    left = None
    if previous is not None and previous.zone != policy.zone:
        left = Elsewhere(
            settings_text.city_of(previous.zone),
            _local(now, previous.zone),
            _local(next_quiet_start(now, policy), previous.zone),
            _local(next_quiet_end(now, policy), previous.zone),
        )
    overview = next_overview(now, policy)
    return Picture(
        headline=headline,
        policy=policy,
        offset_minutes=_minutes(_offset(now, policy.zone)),
        here=_local(now, policy.zone),
        overview_day=_day_word(overview, now, policy),
        overview_clock=_local(overview, policy.zone),
        left=left,
        clock_change=next_clock_change(now, policy.zone),
    )


class Confirmation:
    """Sends the confirmation of a write and handles the Undo button."""

    def __init__(
        self,
        store: SettingsStore,
        chat: DialogChat,
        conversations: ConversationPort,
        by: str,
        now: Callable[[], datetime],
    ) -> None:
        """Wire the settings store, Telegram, the stored conversation, the actor recorded on an Undo and a clock."""
        self._store = store
        self._chat = chat
        self._conversations = conversations
        self._by = by
        self._now = now

    async def confirm(self, headline: str, previous: TimePolicy | None, written: StoredSettings) -> None:
        """Start the Undo conversation for ``written`` and send the full picture with its Undo button."""
        started = await self._conversations.start("settings", None, UNDO_STEP, {"version": written.version}, UNDO_TTL)
        shown = picture(headline, previous, written.policy, self._now())
        undo = button_data("undo", started.nonce)
        await self._chat.send(settings_text.confirmation(shown, undo, settings_text.START_AGAIN))

    async def offer_again(self, conversation: OpenConversation) -> None:
        """Show the Undo button again under the nonce the router just issued."""
        undo = button_data("undo", conversation.nonce)
        await self._chat.send(settings_text.undo_offer(undo, settings_text.START_AGAIN))

    async def undo(self, conversation: OpenConversation) -> None:
        """Put the previous values back if the row is still at the version this confirmation was about."""
        expected = int(str(conversation.partial["version"]))
        before = await self._policy_before()
        try:
            restored = await self._store.undo(expected, "telegram", self._by)
        except VersionConflict:
            await self._end(settings_text.UNDO_CHANGED)
        except NothingToUndo:
            await self._end(settings_text.NOTHING_TO_UNDO)
        except PolicyRefused:
            await self._end(settings_text.UNDO_REFUSED)
        else:
            await self.confirm(settings_text.UNDONE, before, restored)

    async def _policy_before(self) -> TimePolicy | None:
        """The stored policy an Undo replaces, for the comparison; ``None`` if there is no valid row to compare."""
        try:
            stored = await self._store.read()
        except StoredSettingsInvalid:
            return None
        return stored.policy if stored else None

    async def _end(self, note: str) -> None:
        """Nothing was changed: say so, forget the Undo and offer the settings."""
        await self._conversations.clear()
        await self._chat.send(settings_text.with_start_button(note))
