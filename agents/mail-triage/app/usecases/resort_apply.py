"""Apply an approved re-sort plan: swap the ``Assistant/`` label of each approved mail (INT-004).

ADR-0046 points 4 and 8, ADR-0047, spec AC-14, AC-15, AC-18, AC-26, AC-35, AC-39, AC-51, AC-57.

The agent takes ``scheduled`` plans whose ``apply_after`` has passed and works through the approved items in batches.
Before every batch it checks the web lock and compare-and-sets its own claim on the plan, so Lock, Cancel and a second
run stop it before the next batch. For every mail it checks again that the proposed category is still in the list, that
the mail still exists and is in scope, carries exactly the old label and is not pinned. Only then does it change labels,
and only ``Assistant/`` labels, through the narrow Gmail port: nothing is deleted, archived or sent, and ``INBOX`` is
never touched.

A swap is two Gmail calls and a database write. The order makes every crash recoverable:

1. the intent (message id, old and new label id) is written first, once per plan and mail;
2. the new label is added first, so a mail never ends without a label (a crash leaves it with both);
3. the old label is removed;
4. the item is marked applied.

A retry finds the intent. Mail that already carries the new label is checked again as it was before our add (scope,
Archive, pinning and the old label; AC-35): a mail that left the scope meanwhile is skipped and keeps its old label.
Otherwise it is finished (the old label is removed when it is still there, and nothing else is called), so nothing
moves twice. Mail that carries the new label *without* our intent was filed by the user and is skipped.

The notice holds numbers and the names of labels that are empty afterwards (D18); it never holds a sender or subject.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from app.core.judgement import OTHER_ID, OTHER_LABEL
from app.core.resort_plan import ItemState, Plan, PlanNotDueError, PlanState, start_apply
from app.core.scope import LABEL_PREFIX, Scope, classify, clean_display
from app.usecases.triage import pinned_mail_kind

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from app.adapters.gmail_read import FetchedMail
    from app.core.pinned import PinnedSenders
    from app.core.scope import ArchiveLabel

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
    "SkipReason",
    "held_label_ids",
    "label_name_of",
]

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
NAME_MAX = 60
MAX_ITEM_ATTEMPTS = 3  # a mail that fails this often ends ``failed`` and no longer holds back the plan


class MailGone(Exception):  # noqa: N818 - a fact about the mail, not a failure
    """The mail no longer exists in Gmail."""


class MailFailed(Exception):  # noqa: N818 - a fact about one mail, not a failure of the agent
    """Gmail refused or failed an operation on one mail after the adapter's own retries; the mail is not gone."""


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
    """One approved move."""

    message_id: str
    old_category_id: uuid.UUID
    new_category_id: uuid.UUID


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
    """What the audit keeps of one move: Gmail label ids, ``""`` for "no ``Assistant/`` label"."""

    message_id: str
    old_label: str
    new_label: str


class ApplyMailbox(Protocol):
    """Gmail through the narrow adapter. Blocking calls; run in a thread.

    A mail that is gone is ``None`` (fetch) or ``MailGone`` (writes). Any other Gmail failure on one mail is
    ``MailFailed``.
    """

    def label_names(self) -> dict[str, str]:
        """Label id to label name."""
        ...

    def fetch(self, message_id: str) -> FetchedMail | None:
        """Headers and label ids of one mail; ``None`` when it no longer exists."""
        ...

    def ensure_label(self, name: str) -> str:
        """The id of the ``Assistant/`` label ``name``, created when missing (idempotent)."""
        ...

    def add_label(self, message_id: str, label_id: str) -> None:
        """Add one ``Assistant/`` label (idempotent); raises ``MailGone`` when the mail is gone."""
        ...

    def remove_label(self, message_id: str, label_id: str) -> None:
        """Remove one ``Assistant/`` label (idempotent); raises ``MailGone`` when the mail is gone."""
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

    async def current_categories(self) -> dict[str, str]:
        """Category id to name of the current list."""
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


def label_name_of(category_id: str, categories: dict[str, str]) -> str | None:
    """The Gmail label name of a category of the current list; ``None`` when it is not in the list."""
    if category_id == OTHER_ID:
        return OTHER_LABEL
    name = categories.get(category_id)
    return None if name is None else f"{LABEL_PREFIX}{name.strip()}"


def held_label_ids(mail: FetchedMail, names: dict[str, str]) -> set[str]:
    """The ids of the ``Assistant/`` labels on the mail."""
    return {i for i in mail.labels if names.get(i, "").startswith(LABEL_PREFIX)}


@dataclass(frozen=True, slots=True)
class _Checked:
    """A mail that passed every check: the label id to remove ("" for none) and the one to add."""

    old_id: str
    new_label_name: str


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
        archive: ArchiveLabel,  # the protected label (C-14, ADR-0059)
        batch_size: int = BATCH_SIZE,
    ) -> None:
        """Wire the ports, the clock and the allow-list of pinned sender domains."""
        self._mail = mailbox
        self._store = store
        self._lock = lock
        self._notifier = notifier
        self._now = now
        self._pinned = pinned
        self._archive = archive
        self._batch = batch_size

    async def run_once(self) -> None:
        """Work on every plan that is due (or was left ``applying`` by a crashed run)."""
        for due in await self._store.plans_to_apply():
            if due.state is PlanState.SCHEDULED and not self._is_due(due):
                continue
            run_id = uuid.uuid4().hex
            if await self._store.claim(due.plan_id, run_id):
                await self._apply_plan(due, run_id)

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
        categories = await self._store.current_categories()
        names = await asyncio.to_thread(self._mail.label_names)
        for one in items:
            if not await self._apply_item(plan_id, one, categories, names):
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

    async def _apply_item(
        self, plan_id: uuid.UUID, one: ApplyItem, categories: dict[str, str], names: dict[str, str]
    ) -> bool:
        """Move one item; false when Gmail failed and the item stays ``approved`` for a later run.

        A failure is counted and after ``MAX_ITEM_ATTEMPTS`` the item ends ``failed`` (true: it is settled).
        """
        try:
            await self._move_item(plan_id, one, categories, names)
        except MailFailed:
            attempts = await self._store.count_attempt(plan_id, one.message_id)
            logger.warning("item failed plan=%s attempts=%d", plan_id, attempts)
            if attempts >= MAX_ITEM_ATTEMPTS:
                await self._store.finish_item(plan_id, one.message_id, ItemState.FAILED, None)
                return True
            return False
        return True

    async def _move_item(
        self, plan_id: uuid.UUID, one: ApplyItem, categories: dict[str, str], names: dict[str, str]
    ) -> None:
        mid = one.message_id
        new_name = label_name_of(str(one.new_category_id), categories)
        if new_name is None:
            await self._skip(plan_id, mid, SkipReason.CATEGORY_REMOVED)
            return
        mail = await asyncio.to_thread(self._mail.fetch, mid)
        if mail is None:
            await self._skip(plan_id, mid, SkipReason.GONE)
            return
        held = held_label_ids(mail, names)
        intent = await self._store.intent_for(plan_id, mid)
        try:
            if intent is not None and intent.new_label in held:
                await self._retry(plan_id, one, mail, intent, categories, names, held)  # the add happened before
                return
            checked = self._check(one, mail, categories, names, held)
            if isinstance(checked, SkipReason):
                await self._skip(plan_id, mid, checked)
                return
            await self._move(plan_id, mid, checked, names, intent, held)
        except MailGone:
            await self._skip(plan_id, mid, SkipReason.GONE)

    async def _retry(  # noqa: PLR0913, PLR0917
        self,
        plan_id: uuid.UUID,
        one: ApplyItem,
        mail: FetchedMail,
        intent: AuditMove,
        categories: dict[str, str],
        names: dict[str, str],
        held: set[str],
    ) -> None:
        """Finish a swap whose add happened before, unless the mail is no longer one the plan may touch (AC-35).

        The checks run on the mail as it was before our add (without the new label). When the old label is already
        gone, the swap is done and only the item is marked.
        """
        before = held - {intent.new_label}
        if not intent.old_label or intent.old_label in before:
            view = replace(mail, labels=frozenset(i for i in mail.labels if i != intent.new_label))
            checked = self._check(one, view, categories, names, before)
            if isinstance(checked, SkipReason):
                await self._skip(plan_id, mail.message_id, checked)
                return
        await self._finish_started(plan_id, intent, held)

    def _check(
        self, one: ApplyItem, mail: FetchedMail, categories: dict[str, str], names: dict[str, str], held: set[str]
    ) -> _Checked | SkipReason:
        """The checks before a move, in the order that cannot leak: scope, pinning, then the old label."""
        label_names = {names[i] for i in mail.labels if i in names}
        scope = classify(label_names, self._archive.name)
        if scope is Scope.OUT:
            return SkipReason.OUT_OF_SCOPE
        if scope is Scope.UNCLEAR:
            return SkipReason.CHANGED
        if pinned_mail_kind(mail, self._pinned) is not None:
            return SkipReason.PINNED
        old_id = self._old_label_id(str(one.old_category_id), categories, names, held)
        new_name = label_name_of(str(one.new_category_id), categories)
        if old_id is None or new_name is None:
            return SkipReason.CHANGED
        return _Checked(old_id, new_name)

    @staticmethod
    def _old_label_id(
        old_category: str, categories: dict[str, str], names: dict[str, str], held: set[str]
    ) -> str | None:
        """The id of the label to remove ("" when the mail has none); ``None`` when the mail is not where it was.

        "Other" is the category of mail without a label and of mail under the label of a category that left the list.
        """
        if not held:
            return "" if old_category == OTHER_ID else None
        label_id = next(iter(held))
        name = names[label_id]
        if name == label_name_of(old_category, categories):
            return label_id
        listed = {label_name_of(c, categories) for c in categories}
        return label_id if old_category == OTHER_ID and name not in listed else None

    async def _move(  # noqa: PLR0913, PLR0917
        self,
        plan_id: uuid.UUID,
        mid: str,
        checked: _Checked,
        names: dict[str, str],
        intent: AuditMove | None,
        held: set[str],
    ) -> None:
        by_name = {name: label_id for label_id, name in names.items()}
        new_id = by_name.get(checked.new_label_name) or await asyncio.to_thread(
            self._mail.ensure_label, checked.new_label_name
        )
        if intent is None:
            await self._store.record_intent(plan_id, AuditMove(mid, checked.old_id, new_id))
            intent = AuditMove(mid, checked.old_id, new_id)
        await asyncio.to_thread(self._mail.add_label, mid, intent.new_label)
        await self._finish_started(plan_id, intent, held | {intent.new_label})

    async def _finish_started(self, plan_id: uuid.UUID, intent: AuditMove, held: set[str]) -> None:
        """Remove the old label when the mail still carries it, then mark the item applied."""
        if intent.old_label and intent.old_label in held:
            await asyncio.to_thread(self._mail.remove_label, intent.message_id, intent.old_label)
        await self._store.finish_item(plan_id, intent.message_id, ItemState.APPLIED, None)

    async def _skip(self, plan_id: uuid.UUID, message_id: str, reason: SkipReason) -> None:
        logger.info("item skipped plan=%s reason=%s", plan_id, reason)
        await self._store.finish_item(plan_id, message_id, ItemState.SKIPPED, reason)

    async def _report(self, plan_id: uuid.UUID) -> None:
        counts = await self._store.item_counts(plan_id)
        await self._store.remove_applied_items(plan_id)
        empty = await self._empty_labels(plan_id)
        text = (
            f"Plan applied: {counts.get(ItemState.APPLIED, 0)} moved, {counts.get(ItemState.SKIPPED, 0)} skipped"
            + (f", {counts[ItemState.FAILED]} failed" if counts.get(ItemState.FAILED) else "")
            + "."
        )
        if empty:
            text += f" Labels now empty, you can delete them in Gmail: {', '.join(empty)}."
        text += " You can move everything back or lock web sign-in."
        logger.info("plan applied plan=%s counts=%s", plan_id, {k.value: v for k, v in counts.items()})
        await self._notifier.result(text, plan_id=plan_id, offers=(Offer.MOVE_BACK, Offer.LOCK))

    async def _empty_labels(self, plan_id: uuid.UUID) -> list[str]:
        """Names of the labels mail was moved out of that hold no mail now (D18; the agent never deletes labels)."""
        names = await asyncio.to_thread(self._mail.label_names)
        old_ids = sorted({m.old_label for m in await self._store.audit_moves(plan_id) if m.old_label})
        empty: list[str] = []
        for label_id in old_ids:
            if label_id in names and await asyncio.to_thread(self._mail.count_mail, label_id) == 0:
                empty.append(clean_display(names[label_id].removeprefix(LABEL_PREFIX), NAME_MAX))
        return empty
