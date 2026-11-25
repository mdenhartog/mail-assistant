"""The delayed delete of empty labels in the mail cycle (ADR-0060 point 5, spec D6, D7, D10, R1 to R3, R6, R7, R9).

One pass (``run_once``), in this order:

1. PURGE, once per day: the deleted-label record and the finished rename items past the retention go (R7). The
   database decides what is old.
2. GATE: nothing else happens unless the state of the rename plan is ``done`` (a label that is still to be renamed or
   merged must not be touched).
3. SCAN: every Gmail label that is not managed (not in the list, not "Other", not the archive label, not a system
   label) is read from Gmail (type, counts, children) and judged by the pure rule of ``app.core.label_cleanup``:
   start a timer, reset it, let it wait, or mark the label as ripe. A timer of a label that no longer exists goes.
   If Gmail cannot say which labels the filters use (R1), nothing is judged this cycle.
4. DELETE: of the ripe labels, at most ONE is deleted per cycle (the one that waited longest), under a single-writer
   lease (R9). The managed set is read again under the lease: a label that entered the list since the scan is
   skipped. A 404 on the delete call counts as deleted (the label is gone). A label that a re-sort in progress
   targets is skipped. Before the delete the label is checked for mail once more, trash and spam included, and the
   adapter then re-reads it itself, adjacent to the delete call. A refusal
   keeps the timer and the next ripe label is tried (at most ``MAX_ATTEMPTS`` tries); a failing Gmail stops the tries.
   On success the label is recorded (name for the retention, hash of the id) and its timer ends.
5. NOTICE: one Telegram message per day with the count of deleted labels, never a name. The first delete is announced
   in the same cycle; later ones wait for a day to pass since the last message.

The lease is the store's (``CleanupStore.lease``): it is taken for the delete phase only and is never waited for; a
cycle that does not get it goes on without deleting.

Logs, the notice and errors carry counts and codes only, never a label name or the id of a label (AC 29).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from app.adapters.gmail_label_delete import CATEGORY_PREFIX, SYSTEM_IDS, LabelDeleteRefused
from app.adapters.gmail_read import GmailLabelError
from app.core.label_cleanup import Action, LabelFacts, Rules, Timer, decide
from app.core.managed import LabelRef
from app.usecases.list_sync import MigrationState

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager
    from datetime import date, datetime

    from app.adapters.gmail_label_delete import LabelState
    from app.adapters.gmail_read import Label
    from app.core.managed import ManagedSet
    from app.usecases.resort_apply import ResortLabels

__all__ = [
    "MAX_ATTEMPTS",
    "CleanupGmail",
    "CleanupResult",
    "CleanupSettings",
    "CleanupStore",
    "LabelCleanup",
    "LabelLister",
    "StoredTimer",
    "label_id_hash",
]

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # delete tries per cycle: bounds the Gmail calls when labels are refused
NOTICE_EVERY = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class StoredTimer:
    """A row of ``label_empty_since``: when the label was first seen empty, when last, and the wait it started with."""

    empty_since: datetime
    last_seen_empty: datetime
    wait: timedelta

    @property
    def timer(self) -> Timer:
        """The same, as the timer of the rule."""
        return Timer(self.empty_since, self.last_seen_empty, self.wait)


@dataclass(frozen=True, slots=True)
class CleanupSettings:
    """The three agent settings of the cleanup."""

    wait: timedelta
    protection: timedelta
    retention: timedelta


@dataclass(frozen=True, slots=True)
class CleanupResult:
    """What one pass did, as counts."""

    checked: int = 0
    started: int = 0
    reset: int = 0
    waiting: int = 0
    deleted: int = 0
    refused: int = 0
    errors: int = 0  # Gmail failed while reading or deleting
    blocked: bool = False  # the rename plan is not done
    leased_out: bool = False  # another writer held the lease


class _Outcome(Enum):
    DELETED = "deleted"
    REFUSED = "refused"
    FAILED = "failed"


@dataclass(slots=True)
class _Scan:
    """What one scan reads up front and counts on the way."""

    now: datetime
    rules: Rules
    managed: ManagedSet
    left: dict[str, datetime]
    timers: dict[str, StoredTimer]
    filters: frozenset[str]
    checked: int = 0
    started: int = 0
    reset: int = 0
    waiting: int = 0
    refused: int = 0
    errors: int = 0
    ripe: list[tuple[datetime, str]] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)


class LabelLister(Protocol):
    """The part of ``GmailResort`` that lists labels. Blocking."""

    def list_labels(self) -> list[Label]:
        """All labels of the mailbox, read now."""
        ...


class CleanupGmail(Protocol):
    """The part of ``GmailLabelDelete`` the cleanup uses. Blocking calls; run in a thread."""

    def read_label(self, label_id: str) -> LabelState:
        """Type, counts and children of a label, read now."""
        ...

    def labels_in_filters(self) -> frozenset[str]:
        """Every label id that a Gmail filter adds to mail."""
        ...

    def has_mail_including_trash(self, label_id: str) -> bool:
        """Whether one mail with the label exists, spam and trash included."""
        ...

    def delete(self, label_id: str) -> None:
        """Delete the label after its own final checks, or raise ``LabelDeleteRefused``."""
        ...


class CleanupStore(Protocol):
    """The database side of one mailbox."""

    async def migration_state(self) -> MigrationState | None:
        """The state of the rename plan; ``None`` when there is none."""
        ...

    async def settings(self) -> CleanupSettings:
        """The waiting time, the protection period and the retention."""
        ...

    async def managed(self) -> ResortLabels:
        """The managed labels now: the list, "Other" and the archive label."""
        ...

    async def left_list(self) -> dict[str, datetime]:
        """Label id to the time it left the list."""
        ...

    async def resort_label_ids(self) -> frozenset[str]:
        """Label ids a re-sort in progress (an open plan with open items) moves mail from or to."""
        ...

    async def timers(self) -> dict[str, StoredTimer]:
        """Every running timer by label id."""
        ...

    async def start_timer(self, label_id: str, now: datetime, wait: timedelta) -> None:
        """Start a timer with ``wait``; a running timer is not restarted."""
        ...

    async def touch(self, label_id: str, now: datetime) -> None:
        """The label was seen empty at ``now``."""
        ...

    async def clear(self, label_id: str) -> None:
        """Remove the timer."""
        ...

    def lease(self) -> AbstractAsyncContextManager[bool]:
        """The single-writer lease: ``True`` while this caller holds it, ``False`` at once when another does."""
        ...

    async def record_deleted(self, label_id_hash: str, name: str, now: datetime) -> None:
        """Write the deleted label: the hash of its id and its name (kept for the retention)."""
        ...

    async def deleted_since(self, since: datetime) -> int:
        """How many labels were deleted after ``since``."""
        ...

    async def purge_records(self) -> tuple[int, int]:
        """Remove the records past the retention; the counts of deleted-label rows and rename items."""
        ...


class Say(Protocol):
    """The Telegram chat: a plain note."""

    async def say(self, text: str) -> None:
        """Send the note."""
        ...


def label_id_hash(label_id: str) -> str:
    """The sha256 (hex) of a Gmail label id: what the record keeps instead of the id."""
    return hashlib.sha256(label_id.encode()).hexdigest()


class LabelCleanup:
    """The cleanup of one mailbox. The Gmail ports are blocking and are called through threads."""

    def __init__(  # noqa: PLR0913 - the parts are injected for tests
        self,
        labels: LabelLister,
        gmail: CleanupGmail,
        store: CleanupStore,
        chat: Say,
        *,
        now: Callable[[], datetime],
        cycle: timedelta,
    ) -> None:
        """Keep the Gmail ports, the store, the chat, the clock and the time between two cycles."""
        self._labels = labels
        self._gmail = gmail
        self._store = store
        self._chat = chat
        self._now = now
        self._cycle = cycle
        self._purged_on: date | None = None
        self._announced_at: datetime | None = None

    async def run_once(self) -> CleanupResult:
        """One pass; see the module text."""
        now = self._now()
        result = CleanupResult()
        try:
            await self._purge(now)
            if await self._store.migration_state() is not MigrationState.DONE:
                result = CleanupResult(blocked=True)
            else:
                result = await self._cycle_pass(now)
        finally:
            await self._announce(now)
        logger.info(
            "label cleanup: checked=%d started=%d reset=%d waiting=%d deleted=%d refused=%d errors=%d blocked=%s "
            "leased_out=%s",
            result.checked,
            result.started,
            result.reset,
            result.waiting,
            result.deleted,
            result.refused,
            result.errors,
            result.blocked,
            result.leased_out,
        )
        return result

    # --- retention ---------------------------------------------------------------------------------------------

    async def _purge(self, now: datetime) -> None:
        """Once per day; also after a failure (tomorrow retries), and a failure never stops the cleanup."""
        if self._purged_on == now.date():
            return
        self._purged_on = now.date()
        try:
            records, items = await self._store.purge_records()
        except Exception as error:
            logger.warning("label cleanup: the purge failed kind=%s", type(error).__name__)
            return
        logger.info("label cleanup: purged deleted_label=%d rename_items=%d", records, items)

    # --- scan and delete ---------------------------------------------------------------------------------------

    async def _cycle_pass(self, now: datetime) -> CleanupResult:
        settings = await self._store.settings()
        labels = await asyncio.to_thread(self._labels.list_labels)
        try:
            filters = await asyncio.to_thread(self._gmail.labels_in_filters)
        except (LabelDeleteRefused, GmailLabelError) as error:
            logger.warning("label cleanup: the filters could not be read%s", _why(error))
            return CleanupResult(errors=1)  # no filter list, no judgement: a label a filter fills must not go (R1)
        scan = _Scan(
            now=now,
            rules=Rules(settings.wait, settings.protection, self._cycle),
            managed=(await self._store.managed()).managed,
            left=await self._store.left_list(),
            timers=await self._store.timers(),
            filters=filters,
        )
        for label_id in scan.timers.keys() - {label.id for label in labels}:
            await self._store.clear(label_id)  # the label is gone
        for label in labels:
            if label.id not in SYSTEM_IDS and not label.id.startswith(CATEGORY_PREFIX):
                await self._judge(label, scan)
        deleted, refused, errors, leased_out = await self._delete_one(sorted(scan.ripe), scan.names, now)
        return CleanupResult(
            checked=scan.checked,
            started=scan.started,
            reset=scan.reset,
            waiting=scan.waiting,
            deleted=deleted,
            refused=scan.refused + refused,
            errors=scan.errors + errors,
            leased_out=leased_out,
        )

    async def _judge(self, label: Label, scan: _Scan) -> None:
        """Read one label and apply the rule: a timer starts, resets or is touched, or the label is ripe."""
        if scan.managed.find(LabelRef(label.id, label.name)) is not None:
            return  # in the list, "Other" or the archive label: never a candidate
        try:
            state = await asyncio.to_thread(self._gmail.read_label, label.id)
        except LabelDeleteRefused:
            scan.refused += 1
            return
        except GmailLabelError as error:
            logger.warning("label cleanup: a label could not be read%s", _why(error))
            scan.errors += 1
            return
        scan.checked += 1
        scan.names[label.id] = state.name
        facts = LabelFacts(
            label_type=state.type,
            in_list=False,
            has_child=state.has_children,
            messages_total=state.messages_total,
            threads_total=state.threads_total,
            filter_target=label.id in scan.filters,
            left_list_at=scan.left.get(label.id),
        )
        stored = scan.timers.get(label.id)
        decision = decide(facts, None if stored is None else stored.timer, now=scan.now, rules=scan.rules)
        match decision.action:
            case Action.START_TIMER if decision.wait is not None:
                await self._store.start_timer(label.id, scan.now, decision.wait)
                scan.started += 1
            case Action.RESET_TIMER:
                await self._store.clear(label.id)
                scan.reset += 1
            case Action.WAIT:
                await self._store.touch(label.id, scan.now)
                scan.waiting += 1
            case Action.DELETE if stored is not None:
                await self._store.touch(label.id, scan.now)  # a label that waits for its turn is still seen empty
                scan.ripe.append((stored.empty_since, label.id))
            case _:
                pass  # KEEP: nothing is touched; a label that is kept by a blocker keeps its timer rules

    async def _delete_one(
        self, ripe: list[tuple[datetime, str]], names: dict[str, str], now: datetime
    ) -> tuple[int, int, int, bool]:
        """Delete the first label that can go; ``(deleted, refused, errors, leased_out)``."""
        if not ripe:
            return 0, 0, 0, False
        refused = attempts = 0
        async with self._store.lease() as held:
            if not held:
                return 0, 0, 0, True
            candidates = await self._candidates(ripe, names)
            for label_id in candidates:
                if attempts == MAX_ATTEMPTS:
                    break
                attempts += 1
                outcome = await self._try_delete(label_id)
                if outcome is _Outcome.REFUSED:
                    refused += 1
                elif outcome is _Outcome.FAILED:
                    return 0, refused, 1, False  # Gmail is unwell: no more tries this cycle
                else:
                    await self._store.record_deleted(label_id_hash(label_id), names[label_id], now)
                    await self._store.clear(label_id)
                    return 1, refused, 0, False
        return 0, refused, 0, False

    async def _candidates(self, ripe: list[tuple[datetime, str]], names: dict[str, str]) -> list[str]:
        """The ripe label ids that may still go, read under the lease, in the order of their waiting time.

        A cycle that deleted before us cleared its timer; a label a re-sort targets, or that entered the list since
        the scan, stays.
        """
        standing = await self._store.timers()
        targeted = await self._store.resort_label_ids()
        managed = (await self._store.managed()).managed
        return [
            label_id
            for _, label_id in ripe
            if label_id in standing
            and label_id not in targeted
            and managed.find(LabelRef(label_id, names[label_id])) is None
        ]

    async def _try_delete(self, label_id: str) -> _Outcome:
        """The last check for mail (trash and spam included), then the adapter's own checks and the delete call."""
        try:
            if await asyncio.to_thread(self._gmail.has_mail_including_trash, label_id):
                return _Outcome.REFUSED
            await asyncio.to_thread(self._gmail.delete, label_id)
        except LabelDeleteRefused:
            return _Outcome.REFUSED  # the adapter logged the code; the timer stays
        except GmailLabelError as error:
            logger.warning("label cleanup: the delete failed%s", _why(error))
            return _Outcome.FAILED
        return _Outcome.DELETED

    # --- notice ------------------------------------------------------------------------------------------------

    async def _announce(self, now: datetime) -> None:
        """One note per day with the count; a failure is logged by type and the next cycle tries again."""
        if self._announced_at is not None and now - self._announced_at < NOTICE_EVERY:
            return
        try:
            count = await self._store.deleted_since(self._announced_at or now - NOTICE_EVERY)
            if count == 0:
                return
            noun = "empty label was" if count == 1 else "empty labels were"
            await self._chat.say(
                f"Label cleanup: {count} {noun} deleted since the last note. The names are on the Categories page."
            )
            self._announced_at = now
        except Exception as error:
            logger.warning("label cleanup: the notice was not sent kind=%s", type(error).__name__)


def _why(error: Exception) -> str:
    """The status of a Gmail failure; never Gmail's text or a name."""
    status = getattr(error, "status", None)
    return f" status={status}" if isinstance(status, int) else ""
