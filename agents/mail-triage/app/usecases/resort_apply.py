"""Apply an approved re-sort plan: swap the managed labels of each approved mail (INT-004, INT-010).

ADR-0046 points 4 and 8, ADR-0047, ADR-0060, spec AC-14, AC-15, AC-18, AC-26, AC-35, AC-39, AC-51, AC-57.

The agent takes ``scheduled`` plans whose ``apply_after`` has passed and works through the approved items in batches.
Before every batch it checks the web lock and compare-and-sets its own claim on the plan, so Lock, Cancel and a second
run stop it before the next batch. For every mail it checks again that the proposed category is still in the list, that
the mail still exists and is in scope, carries exactly the old label and is not pinned. Only then does it change labels,
and only managed labels (the category list, "Other" and the archive label, by Gmail label id; ADR-0060), through the
narrow Gmail port: nothing is deleted, archived or sent, and ``INBOX`` is never touched. Scope is decided by label id: a
label that is not managed never puts a mail in scope and is never added or removed, and the archive label wins.

A swap is two Gmail calls and a database write. The order makes every crash recoverable:

1. the intent (message id, old and new label id) is written first, once per plan and mail;
2. the new label is added first, so a mail never ends without a label (a crash leaves it with both);
3. the old label is removed;
4. the item is marked applied.

A retry finds the intent. Mail that already carries the new label is checked again as it was before our add (scope,
Archive, pinning and the old label; AC-35): a mail that left the scope meanwhile is skipped and keeps its old label.
Otherwise it is finished (the old label is removed when it is still there, and nothing else is called), so nothing
moves twice. Mail that carries the new label *without* our intent was filed by the user and is skipped.

Pairs (D13, U-label-structure-23): an item moves a mail from one pair (topic, extra label) to another. The labels of a
pair are a set of at most two Gmail labels; the audit row holds the set before and after as label ids joined with
commas (``label_ids``), and the swap adds the labels the new pair gains and removes the ones the old pair loses. A mail
is checked against the whole old pair, so a mail whose extra label the user changed meanwhile is skipped like any other
changed mail. A plan whose target category left the list (an upload or a rename, D20) is cancelled before it moves
anything.

The notice holds numbers only, the count of labels that are empty afterwards included; it never holds a label name,
a sender or a subject (ADR-0060 point 8).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from app.core import approval_text
from app.core.judgement import OTHER_ID
from app.core.mail_errors import LabelWritesHeld, MailFailed, MailGone
from app.core.managed import LabelRef, ManagedLabel, ManagedSet, Role
from app.core.pinned import pinned_kind
from app.core.resort_plan import ItemState, Plan, PlanNotDueError, PlanState, start_apply
from app.core.scope import Scope, classify

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from datetime import datetime

    from app.adapters.gmail_read import FetchedMail
    from app.core.pinned import PinnedSenders

__all__ = [
    "BATCH_SIZE",
    "MAX_ITEM_ATTEMPTS",
    "ApplyItem",
    "ApplyLock",
    "ApplyMailbox",
    "ApplyNotifier",
    "ApplyStore",
    "AuditMove",
    "DuePlan",
    "MailFailed",
    "MailGone",
    "Offer",
    "ResortApply",
    "ResortLabels",
    "SkipReason",
    "held_label_ids",
    "join_label_ids",
    "label_ids",
]

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
MAX_ITEM_ATTEMPTS = 3  # a mail that fails this often ends ``failed`` and no longer holds back the plan


@dataclass(frozen=True, slots=True)
class ResortLabels:
    """The managed labels of one moment (ADR-0060): the set that decides scope, and the label of each category.

    ``by_category`` maps a category id of the current list to its managed label; ``OTHER_ID`` maps to the "Other"
    label of the settings. The archive label is in ``managed`` only (it is never a target). A label whose Gmail id is
    not stored yet has ``label_id`` ``None`` and is created or adopted by name when a move needs it.
    """

    managed: ManagedSet
    by_category: Mapping[str, ManagedLabel]

    def category_of(self, label: ManagedLabel) -> str | None:
        """The category id a managed label stands for; ``None`` for the archive label."""
        return next((cid for cid, found in self.by_category.items() if found == label), None)


class SkipReason(StrEnum):
    """Why an approved item was not moved (shown on the page)."""

    GONE = "gone"
    OUT_OF_SCOPE = "out_of_scope"  # deleted to trash or spam, archived, left the inbox
    CHANGED = "changed"  # carries another label than the old one
    CATEGORY_REMOVED = "category_removed"
    PINNED = "pinned"


class Offer(StrEnum):
    """The buttons of the result notice (ADR-0046 point 7)."""

    MOVE_BACK = "move_back"
    LOCK = "lock"


@dataclass(frozen=True, slots=True)
class ApplyItem:
    """One approved move of the pair (old topic, old extra) to the pair (new topic, new extra)."""

    message_id: str
    old_topic_id: uuid.UUID
    new_topic_id: uuid.UUID
    old_extra_id: uuid.UUID | None = None
    new_extra_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class DuePlan:
    """A plan the agent may have to work on, with who approved it (for the audit rows)."""

    plan_id: uuid.UUID
    state: PlanState
    apply_after: datetime | None
    channel: str
    actor_digest: str


@dataclass(frozen=True, slots=True)
class AuditMove:
    """What the audit keeps of one move: the Gmail label ids of the pair (``label_ids``), ``""`` for no label."""

    message_id: str
    old_label: str
    new_label: str


class ApplyMailbox(Protocol):
    """Gmail through the narrow adapter. Blocking calls; run in a thread.

    A mail that is gone is ``None`` (fetch) or ``MailGone`` (writes). Any other Gmail failure on one mail is
    ``MailFailed``.
    """

    def set_managed(self, managed: ManagedSet) -> None:
        """Use the managed labels of this batch: the adapter only changes labels of this set, by id."""
        ...

    def label_names(self) -> dict[str, str]:
        """Label id to label name."""
        ...

    def fetch(self, message_id: str) -> FetchedMail | None:
        """Headers and label ids of one mail; ``None`` when it no longer exists."""
        ...

    def ensure_label(self, label: ManagedLabel) -> str:
        """The id of the managed label, created or adopted by name when it has none yet (idempotent)."""
        ...

    def add_label(self, message_id: str, label_id: str) -> str:
        """Add one managed label (idempotent), return the id used; raises ``MailGone`` when the mail is gone."""
        ...

    def remove_label(self, message_id: str, label_id: str) -> None:
        """Remove one managed label (idempotent); raises ``MailGone`` when the mail is gone."""
        ...

    def count_mail(self, label_id: str) -> int:
        """The number of mails that carry the label."""
        ...


class ApplyLock(Protocol):
    """The web lock."""

    async def is_locked(self) -> bool:
        """Whether web sign-in is locked."""
        ...


class ApplyNotifier(Protocol):
    """Telegram."""

    async def say(self, text: str) -> None:
        """Send a plain note."""
        ...

    async def result(self, text: str, *, plan_id: uuid.UUID, offers: tuple[Offer, ...]) -> None:
        """Send the result notice with buttons; each button gets its own nonce (ADR-0046 point 7)."""
        ...


class ApplyStore(Protocol):
    """The plan tables as the apply needs them. Every write that changes state is a compare-and-set."""

    async def plans_to_apply(self) -> list[DuePlan]:
        """Plans that are ``scheduled`` or ``applying`` (the latter to resume after a crash)."""
        ...

    async def claim(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """``scheduled`` to ``applying``, or take over an ``applying`` plan whose lease ended; one caller wins."""
        ...

    async def begin_batch(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """True while the plan is still ``applying`` and this run holds the lease; renews the lease."""
        ...

    async def cancel(self, plan_id: uuid.UUID) -> bool:
        """``scheduled`` or ``applying`` to ``cancelled`` (Lock); false when it was already something else."""
        ...

    async def managed_labels(self) -> ResortLabels:
        """The managed labels now: the current list, the "Other" setting and the archive label (ADR-0060)."""
        ...

    async def target_ids(self, plan_id: uuid.UUID) -> frozenset[str]:
        """The ids of the categories the items still ``approved`` move mail into (new topic and new extra)."""
        ...

    async def next_items(self, plan_id: uuid.UUID, limit: int) -> list[ApplyItem]:
        """Up to ``limit`` items still ``approved``."""
        ...

    async def intent_for(self, plan_id: uuid.UUID, message_id: str) -> AuditMove | None:
        """The audit row of this plan and mail, when one exists."""
        ...

    async def record_intent(self, plan_id: uuid.UUID, move: AuditMove) -> None:
        """Insert the audit row (channel and actor of the approval) unless one exists for plan and mail."""
        ...

    async def count_attempt(self, plan_id: uuid.UUID, message_id: str) -> int:
        """Count one failed move of an item still ``approved`` and return how many failed so far."""
        ...

    async def finish_item(
        self, plan_id: uuid.UUID, message_id: str, state: ItemState, reason: SkipReason | None
    ) -> bool:
        """Compare-and-set ``approved`` to ``applied``, ``skipped`` or ``failed`` with the reason."""
        ...

    async def finish_plan(self, plan_id: uuid.UUID, run_id: str) -> bool:
        """Compare-and-set ``applying`` to ``applied`` for the lease holder; true for exactly one caller."""
        ...

    async def item_counts(self, plan_id: uuid.UUID) -> dict[ItemState, int]:
        """Items per state."""
        ...

    async def remove_applied_items(self, plan_id: uuid.UUID) -> None:
        """Delete the applied items (skipped ones stay for the page)."""
        ...

    async def audit_moves(self, plan_id: uuid.UUID) -> list[AuditMove]:
        """The apply rows of the plan (not the rows a move back wrote)."""
        ...


def held_label_ids(mail: FetchedMail, names: dict[str, str], managed: ManagedSet) -> set[str]:
    """The ids of the managed labels on the mail (the archive label too: it is managed, and it wins elsewhere)."""
    return {i for i in mail.labels if managed.find(LabelRef(i, names.get(i, ""))) is not None}


def label_ids(text: str) -> frozenset[str]:
    """The Gmail label ids of an audit field (``""`` is no label); the inverse of ``join_label_ids``."""
    return frozenset(part for part in text.split(",") if part)


def join_label_ids(ids: Iterable[str]) -> str:
    """The audit field of a set of Gmail label ids: sorted and joined with commas (ids never hold a comma)."""
    return ",".join(sorted(ids))


@dataclass(frozen=True, slots=True)
class _Checked:
    """A mail that passed every check: the labels it holds now (the old pair) and the managed labels of the new pair."""

    old_ids: frozenset[str]
    new_labels: tuple[ManagedLabel, ...]


def _added(move: AuditMove) -> set[str]:
    """The labels a move gains: those of the new pair the old pair did not have."""
    return set(label_ids(move.new_label) - label_ids(move.old_label))


@dataclass(frozen=True, slots=True)
class _View:
    """The managed labels and the label table as one batch of items sees them."""

    labels: ResortLabels
    names: dict[str, str]  # Gmail label id to name

    def refs(self, mail: FetchedMail) -> list[LabelRef]:
        """The labels of a mail as ``classify`` wants them: id and current name."""
        return [LabelRef(i, self.names.get(i, "")) for i in mail.labels]

    def managed_label(self, label_id: str) -> ManagedLabel | None:
        """The managed label with this Gmail id (by name only while its id is not stored)."""
        return self.labels.managed.find(LabelRef(label_id, self.names.get(label_id, "")))

    def new_labels(self, one: ApplyItem) -> tuple[ManagedLabel, ...] | None:
        """The managed labels of the new pair; ``None`` when a target category left the list."""
        topic = self.labels.by_category.get(str(one.new_topic_id))
        extra = None if one.new_extra_id is None else self.labels.by_category.get(str(one.new_extra_id))
        if topic is None or (one.new_extra_id is not None and extra is None):
            return None
        return (topic,) if extra is None else (topic, extra)

    def holds_old_pair(self, one: ApplyItem, held: set[str]) -> bool:
        """Whether the mail carries exactly the old pair: its topic label (or none, for Other) and its extra label."""
        found = {i: self.managed_label(i) for i in held}
        extras = {i for i, label in found.items() if label is not None and label.role is Role.EXTRA}
        topics = held - extras
        return self._topic_matches(str(one.old_topic_id), [found[i] for i in topics]) and self._extra_matches(
            one.old_extra_id, [found[i] for i in extras]
        )

    def _topic_matches(self, old_topic: str, topics: list[ManagedLabel | None]) -> bool:
        if not topics:
            return old_topic == OTHER_ID  # Other is the topic of mail without a topic label
        wanted = self.labels.by_category.get(old_topic)
        return wanted is not None and topics == [wanted]

    def _extra_matches(self, old_extra: uuid.UUID | None, extras: list[ManagedLabel | None]) -> bool:
        if old_extra is None:
            return not extras
        wanted = self.labels.by_category.get(str(old_extra))
        return wanted is not None and extras == [wanted]


class ResortApply:
    """Applies the approved items of due plans, a batch at a time."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        mailbox: ApplyMailbox,
        store: ApplyStore,
        lock: ApplyLock,
        notifier: ApplyNotifier,
        now: Callable[[], datetime],
        pinned: PinnedSenders,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        """Wire the ports, the clock and the allow-list of pinned sender domains."""
        self._mail = mailbox
        self._store = store
        self._lock = lock
        self._notifier = notifier
        self._now = now
        self._pinned = pinned
        self._batch = batch_size

    async def run_once(self) -> None:
        """Work on every plan that is due (or was left ``applying`` by a crashed run)."""
        for due in await self._store.plans_to_apply():
            if await self._cancel_if_target_removed(due):
                continue
            if due.state is PlanState.SCHEDULED and not self._is_due(due):
                continue
            run_id = uuid.uuid4().hex
            if await self._store.claim(due.plan_id, run_id):
                await self._apply_plan(due, run_id)

    async def _cancel_if_target_removed(self, due: DuePlan) -> bool:
        """Cancel a plan that moves mail into a category the current list no longer has (D20, AC-51).

        An upload or a rename that removes a target cancels the plan; a list save that keeps every target lets it
        finish. True when the plan was cancelled (now or by someone else meanwhile: it is not ours to apply).
        """
        labels = (await self._store.managed_labels()).by_category
        targets = await self._store.target_ids(due.plan_id)
        if all(t == OTHER_ID or t in labels for t in targets):
            return False
        if await self._store.cancel(due.plan_id):
            logger.info("plan cancelled: a target category left the list plan=%s", due.plan_id)
            await self._notifier.say(approval_text.TARGET_REMOVED)
        return True

    def _is_due(self, due: DuePlan) -> bool:
        try:
            start_apply(Plan(due.state, due.apply_after, self._now()), now=self._now())
        except PlanNotDueError:
            return False
        return True

    async def _run_batch(self, plan_id: uuid.UUID, waiting: set[str]) -> bool:
        """Apply the next batch of approved items; false when none is left. Items that fail join ``waiting``."""
        found = await self._store.next_items(plan_id, self._batch + len(waiting))
        items = [one for one in found if one.message_id not in waiting][: self._batch]
        if not items:
            return False
        labels = await self._store.managed_labels()
        self._mail.set_managed(labels.managed)
        names = await asyncio.to_thread(self._mail.label_names)
        view = _View(labels, names)
        for one in items:
            if not await self._apply_item(plan_id, one, view):
                waiting.add(one.message_id)
        return True

    async def _apply_plan(self, due: DuePlan, run_id: str) -> None:
        plan_id = due.plan_id
        waiting: set[str] = set()  # failed in this run: tried again in a later run, never at once (REV-005)
        while True:
            if await self._lock.is_locked():
                await self._store.cancel(plan_id)
                logger.info("apply stopped by the lock plan=%s", plan_id)
                return
            if not await self._store.begin_batch(plan_id, run_id):
                logger.info("apply stopped: the plan is no longer ours plan=%s", plan_id)
                return
            if not await self._run_batch(plan_id, waiting):
                break
        if waiting:
            # The plan stays ``applying`` and its lease ends by itself: the next run is the next try for these items.
            logger.info("apply paused: %d item(s) wait for the next run plan=%s", len(waiting), plan_id)
            return
        if await self._store.finish_plan(plan_id, run_id):
            await self._report(plan_id)

    async def _apply_item(self, plan_id: uuid.UUID, one: ApplyItem, view: _View) -> bool:
        """Move one item; false when Gmail failed and the item stays ``approved`` for a later run.

        A failure is counted and after ``MAX_ITEM_ATTEMPTS`` the item ends ``failed`` (true: it is settled).
        """
        try:
            await self._move_item(plan_id, one, view)
        except LabelWritesHeld:  # the rename plan is not done: wait, no attempt is counted and no label is made (R4)
            logger.info("item waits for the rename plan plan=%s", plan_id)
            return False
        except MailFailed:
            attempts = await self._store.count_attempt(plan_id, one.message_id)
            logger.warning("item failed plan=%s attempts=%d", plan_id, attempts)
            if attempts >= MAX_ITEM_ATTEMPTS:
                await self._store.finish_item(plan_id, one.message_id, ItemState.FAILED, None)
                return True
            return False
        return True

    async def _move_item(self, plan_id: uuid.UUID, one: ApplyItem, view: _View) -> None:
        mid = one.message_id
        if view.new_labels(one) is None:
            await self._skip(plan_id, mid, SkipReason.CATEGORY_REMOVED)
            return
        mail = await asyncio.to_thread(self._mail.fetch, mid)
        if mail is None:
            await self._skip(plan_id, mid, SkipReason.GONE)
            return
        held = held_label_ids(mail, view.names, view.labels.managed)
        intent = await self._store.intent_for(plan_id, mid)
        try:
            if intent is not None and _added(intent) <= held:
                await self._retry(plan_id, one, mail, intent, view, held)  # the add happened before
                return
            checked = self._check(one, mail, view, held)
            if isinstance(checked, SkipReason):
                await self._skip(plan_id, mid, checked)
                return
            await self._move(plan_id, mid, checked, view, intent, held)
        except MailGone:
            await self._skip(plan_id, mid, SkipReason.GONE)

    async def _retry(  # noqa: PLR0913, PLR0917
        self,
        plan_id: uuid.UUID,
        one: ApplyItem,
        mail: FetchedMail,
        intent: AuditMove,
        view: _View,
        held: set[str],
    ) -> None:
        """Finish a swap whose add happened before, unless the mail is no longer one the plan may touch (AC-35).

        The checks run on the mail as it was before our add (without the labels we added). When an old label is
        already gone, the swap is under way and only the rest is finished.
        """
        added = _added(intent)
        before = held - added
        if label_ids(intent.old_label) <= before:
            seen = replace(mail, labels=frozenset(i for i in mail.labels if i not in added))
            checked = self._check(one, seen, view, before)
            if isinstance(checked, SkipReason):
                await self._skip(plan_id, mail.message_id, checked)
                return
        await self._finish_started(plan_id, intent, held)

    def _check(self, one: ApplyItem, mail: FetchedMail, view: _View, held: set[str]) -> _Checked | SkipReason:
        """The checks before a move, in the order that cannot leak: scope, pinning, then the old pair."""
        scope = classify(view.refs(mail), view.labels.managed)
        if scope is Scope.OUT:
            return SkipReason.OUT_OF_SCOPE
        if scope is Scope.UNCLEAR:
            return SkipReason.CHANGED
        if pinned_kind(mail.auth_results, mail.sender, self._pinned) is not None:
            return SkipReason.PINNED
        new_labels = view.new_labels(one)
        if new_labels is None or not view.holds_old_pair(one, held):
            return SkipReason.CHANGED
        return _Checked(frozenset(held), new_labels)

    async def _move(  # noqa: PLR0913, PLR0917
        self,
        plan_id: uuid.UUID,
        mid: str,
        checked: _Checked,
        view: _View,
        intent: AuditMove | None,
        held: set[str],
    ) -> None:
        if intent is None:
            new_ids = {
                label.label_id or await asyncio.to_thread(self._mail.ensure_label, label)
                for label in checked.new_labels
            }
            intent = AuditMove(mid, join_label_ids(checked.old_ids), join_label_ids(new_ids))
            await self._store.record_intent(plan_id, intent)
        gained = _added(intent)
        for label_id in sorted(gained - held):
            await asyncio.to_thread(self._mail.add_label, mid, label_id)
        await self._finish_started(plan_id, intent, held | gained)

    async def _finish_started(self, plan_id: uuid.UUID, intent: AuditMove, held: set[str]) -> None:
        """Remove the old labels the mail still carries and the new pair does not need, then mark the item applied."""
        for label_id in sorted((label_ids(intent.old_label) - label_ids(intent.new_label)) & held):
            await asyncio.to_thread(self._mail.remove_label, intent.message_id, label_id)
        await self._store.finish_item(plan_id, intent.message_id, ItemState.APPLIED, None)

    async def _skip(self, plan_id: uuid.UUID, message_id: str, reason: SkipReason) -> None:
        logger.info("item skipped plan=%s reason=%s", plan_id, reason)
        await self._store.finish_item(plan_id, message_id, ItemState.SKIPPED, reason)

    async def _report(self, plan_id: uuid.UUID) -> None:
        counts = await self._store.item_counts(plan_id)
        await self._store.remove_applied_items(plan_id)
        empty = await self._count_empty_labels(plan_id)
        text = (
            f"Plan applied: {counts.get(ItemState.APPLIED, 0)} moved, {counts.get(ItemState.SKIPPED, 0)} skipped"
            + (f", {counts[ItemState.FAILED]} failed" if counts.get(ItemState.FAILED) else "")
            + "."
        )
        if empty:
            text += f" Labels that are empty now: {empty}."
        text += f" You can move everything back or lock web sign-in. {approval_text.LOCK_EXPLAINED}"
        logger.info("plan applied plan=%s counts=%s", plan_id, {k.value: v for k, v in counts.items()})
        await self._notifier.result(text, plan_id=plan_id, offers=(Offer.MOVE_BACK, Offer.LOCK))

    async def _count_empty_labels(self, plan_id: uuid.UUID) -> int:
        """How many labels mail was moved out of hold no mail now (a count: a notice never names a label)."""
        names = await asyncio.to_thread(self._mail.label_names)
        old_ids = sorted({i for m in await self._store.audit_moves(plan_id) for i in label_ids(m.old_label)})
        empty = 0
        for label_id in old_ids:
            if label_id in names and await asyncio.to_thread(self._mail.count_mail, label_id) == 0:
                empty += 1
        return empty
