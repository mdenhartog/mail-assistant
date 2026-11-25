"""The one-off rename of the old labels: build the plan, wait for the confirmation, run it, restore it (ADR-0061).

One pass (``run_once``), in this order:

1. BUILD: only when the state is ``pending`` and no item exists. The plan is written once; the database hashes it
   (``label_plan_hash``) and stores the hash. Nothing is renamed. A plan without items goes straight to ``done``.
2. RESTORE: an open restore request while the state is ``confirmed`` or ``done``. Every waiting item is given up
   (``kept``), every renamed label that still carries its new name gets the old name back by id, a label that changed
   since is left alone. A merge is not undone: which mail the merge moved is not recorded (a mail id is mail data), so
   the mail stays on the existing label. The request is closed when nothing is left to retry.
3. RUN: only when the state is ``confirmed`` and a confirmation exists (AC 5). Items in ``skipped_ids`` are set
   ``skipped`` and never touched. For every other planned item the label is read again by id first; a label that is
   gone or no longer has the planned old name is ``kept`` (AC 26). A rename patches the name only (colour and
   visibility stay). A merge adds the existing label to every mail of the old label and then removes the old label
   from it, page by page: the add comes first, so a crash never loses mail, and a rerun finds the rest. Each item is
   settled in the database as soon as it is done, so a crash resumes with the rest. Only when no item waits does the
   state become ``done``; then (once) one notice with counts is sent.

Guard: the old labels are not in the managed set of the list. For each item the adapter's managed set is replaced by
exactly the labels of that item (the old label, and the merge target for a merge), with role ``LEGACY``; it is emptied
at the end of the pass. Nothing else can be changed through the adapter meanwhile (it refuses with ``LabelRefused``).

Notice and logs hold counts only, never a label name, mail or Gmail's message (AC 18, 29).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from dataclasses import dataclass
from enum import StrEnum
from itertools import batched
from typing import TYPE_CHECKING, Literal, Protocol

from googleapiclient.errors import HttpError

from app.adapters.gmail_resort import GmailLabelError, Label, LabelNameRejected, LabelNameTaken, LabelRefused
from app.core.managed import LabelRef, ManagedLabel, ManagedSet, Role
from app.core.rename_plan import build_plan
from app.usecases.list_sync import ManagedSink, MigrationState

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.rename_plan import PlanItem

__all__ = ["ItemState", "LabelRename", "RenameGmail", "RenameResult", "RenameStore", "StoredItem"]

logger = logging.getLogger(__name__)

PAGE_SIZE = 100  # mails moved per thread call of a merge
MAX_MERGE_PASSES = 3  # a mail that arrives with the old label while a merge runs is picked up by the next pass


class ItemState(StrEnum):
    """The state of one plan item (``label_rename_item.state``)."""

    PLANNED = "planned"
    SKIPPED = "skipped"  # the user skipped it in the preview
    DONE = "done"
    KEPT = "kept"  # left as it is: it changed, was refused, or the user restored it


@dataclass(frozen=True, slots=True)
class StoredItem:
    """A plan item as the database has it."""

    label_id: str
    old_name: str
    new_name: str
    mail_count: int
    action: Literal["rename", "merge"]
    state: ItemState


@dataclass(frozen=True, slots=True)
class RenameResult:
    """What one pass did, as counts."""

    built: int = 0
    renamed: int = 0
    merged: int = 0
    skipped: int = 0
    kept: int = 0
    failed: int = 0  # items left planned for the next pass
    restored: int = 0
    merges_left: int = 0
    completed: bool = False


class Say(Protocol):
    """The Telegram chat: a plain note."""

    async def say(self, text: str) -> None:
        """Send the note."""
        ...


class RenameGmail(ManagedSink, Protocol):
    """The part of ``GmailResort`` the rename uses. Blocking calls; run in a thread."""

    def list_labels(self) -> list[Label]:
        """All labels, read now."""
        ...

    def count_mail(self, label_id: str) -> int:
        """The mails under a label."""
        ...

    def list_mail(self, label_id: str) -> list[str]:
        """The ids of the mails under a label."""
        ...

    def add_label(self, message_id: str, label_id: str) -> str:
        """Add a label to a mail."""
        ...

    def remove_label(self, message_id: str, label_id: str) -> None:
        """Remove a label from a mail."""
        ...

    def rename_label(self, label_id: str, new_name: str) -> Label:
        """Rename a label by id."""
        ...


class RenameStore(Protocol):
    """The database side of one mailbox."""

    async def migration_state(self) -> MigrationState | None:
        """The state of the plan; ``None`` when the mailbox has none."""
        ...

    async def items(self) -> list[StoredItem]:
        """Every plan item."""
        ...

    async def write_plan(self, items: Sequence[PlanItem]) -> int:
        """Write the plan and its hash when the state is ``pending`` and no item exists; return the items written.

        A plan without items moves the state to ``done``.
        """
        ...

    async def skipped_ids(self) -> frozenset[str] | None:
        """The ids the user skipped; ``None`` while there is no confirmation."""
        ...

    async def settle(self, label_id: str, to: ItemState, *, was: ItemState) -> None:
        """Move one item from ``was`` to ``to``; an item in another state is left as it is."""
        ...

    async def complete(self) -> bool:
        """``confirmed`` to ``done`` when no item is planned; True when this call made the change."""
        ...

    async def open_restore(self) -> str | None:
        """The id of the open restore request, if any."""
        ...

    async def close_restore(self, request_id: str) -> None:
        """Mark the request processed."""
        ...

    async def archive_name(self) -> str:
        """The name of the archive label in the latest list version."""
        ...

    async def protected_ids(self) -> frozenset[str]:
        """The stored Gmail label ids of "Other" and the archive label: never the target of a merge."""
        ...


class _Retry(Exception):  # noqa: N818 - control flow inside this module: the item stays planned
    """Gmail failed in a way that may pass; the item is tried again in the next pass."""


class LabelRename:
    """The rename plan of one mailbox. ``gmail`` is blocking and is called through threads."""

    def __init__(self, gmail: RenameGmail, store: RenameStore, chat: Say, *, page_size: int = PAGE_SIZE) -> None:
        """Keep the Gmail adapter, the store, the chat and the merge page size."""
        self._gmail = gmail
        self._store = store
        self._chat = chat
        self._page = page_size

    async def run_once(self) -> RenameResult:
        """One pass; see the module text."""
        state = await self._store.migration_state()
        if state is None:
            return RenameResult()
        try:
            result = await self._pass(state)
        finally:
            self._gmail.set_managed(ManagedSet(()))  # nothing stays allowed after the pass
        logger.info(
            "label rename: built=%d renamed=%d merged=%d skipped=%d kept=%d failed=%d restored=%d "
            "merges_left=%d completed=%s",
            result.built,
            result.renamed,
            result.merged,
            result.skipped,
            result.kept,
            result.failed,
            result.restored,
            result.merges_left,
            result.completed,
        )
        return result

    async def _pass(self, state: MigrationState) -> RenameResult:
        built = await self._build() if state is MigrationState.PENDING else 0
        result = RenameResult(built=built)
        state = await self._store.migration_state() or state
        if state is not MigrationState.PENDING and (request := await self._store.open_restore()) is not None:
            result = await self._restore(request, result)
            state = await self._store.migration_state() or state
        if state is MigrationState.CONFIRMED:
            result = await self._apply(result)
        return result

    # --- build -------------------------------------------------------------------------------------------------

    async def _build(self) -> int:
        if await self._store.items():
            return 0  # the plan was built; it waits for the confirmation
        labels = await asyncio.to_thread(self._gmail.list_labels)
        plan = build_plan(LabelRef(label.id, label.name) for label in labels)
        counted = [
            dataclasses.replace(item, mail_count=await asyncio.to_thread(self._gmail.count_mail, item.label_id))
            for item in plan
        ]
        return await self._store.write_plan(counted)

    # --- run ---------------------------------------------------------------------------------------------------

    async def _apply(self, result: RenameResult) -> RenameResult:
        skipped_ids = await self._store.skipped_ids()
        if skipped_ids is None:
            return result  # no confirmation row: nothing is renamed (AC 5)
        archive = (await self._store.archive_name()).casefold()
        protected = await self._store.protected_ids()
        failed = 0
        for item in [i for i in await self._store.items() if i.state is ItemState.PLANNED]:
            if item.label_id in skipped_ids:
                await self._store.settle(item.label_id, ItemState.SKIPPED, was=ItemState.PLANNED)
                continue
            try:
                outcome = await self._item(item, archive, protected)
            except _Retry:
                failed += 1
                continue
            await self._store.settle(item.label_id, outcome, was=ItemState.PLANNED)
        completed = await self._store.complete()
        totals = await self._store.items()
        result = dataclasses.replace(
            result,
            renamed=_count(totals, ItemState.DONE, "rename"),
            merged=_count(totals, ItemState.DONE, "merge"),
            skipped=_count(totals, ItemState.SKIPPED),
            kept=_count(totals, ItemState.KEPT),
            failed=failed,
            completed=completed,
        )
        if completed:
            await self._notify(
                f"Label cleanup is done: {result.renamed} renamed, {result.merged} merged into an existing label, "
                f"{result.skipped} skipped by you, {result.kept} left as they were."
            )
        return result

    async def _item(self, item: StoredItem, archive: str, protected: frozenset[str]) -> ItemState:
        """Do one item; ``DONE`` or ``KEPT``. Raises ``_Retry`` when Gmail failed in a way that may pass."""
        labels = await asyncio.to_thread(self._gmail.list_labels)  # read again, by id, just before the change
        verdict = _check(item, labels, archive, protected)
        if isinstance(verdict, ItemState):
            return verdict
        old, target = verdict
        self._gmail.set_managed(ManagedSet([ManagedLabel(old.name, old.id, Role.LEGACY), *_legacy(target)]))
        try:
            if target is None:
                await asyncio.to_thread(self._gmail.rename_label, item.label_id, item.new_name)
            else:
                await self._merge(item.label_id, target.id)
        except (LabelRefused, LabelNameRejected, LabelNameTaken):
            return ItemState.KEPT
        except (GmailLabelError, HttpError) as error:
            logger.warning("label rename: an item failed kind=%s%s", type(error).__name__, _status(error))
            raise _Retry from None
        return ItemState.DONE

    async def _merge(self, old_id: str, target_id: str) -> None:
        """Move the mail of the old label onto the target, in pages; add first, then remove, so no mail is lost."""
        for _ in range(MAX_MERGE_PASSES):
            ids = await asyncio.to_thread(self._gmail.list_mail, old_id)
            if not ids:
                return
            for page in batched(ids, self._page):
                await asyncio.to_thread(self._move, page, old_id, target_id)
        if await asyncio.to_thread(self._gmail.list_mail, old_id):
            raise _Retry

    def _move(self, page: Sequence[str], old_id: str, target_id: str) -> None:
        for message_id in page:
            try:
                self._gmail.add_label(message_id, target_id)
                self._gmail.remove_label(message_id, old_id)
            except HttpError as error:
                if getattr(error.resp, "status", 0) != HTTP_NOT_FOUND:
                    raise  # a mail that is gone has nothing to move; anything else is a failure of the item

    # --- restore -----------------------------------------------------------------------------------------------

    async def _restore(self, request_id: str, result: RenameResult) -> RenameResult:
        restored = merges = changed = failed = 0
        for item in await self._store.items():
            if item.state is ItemState.PLANNED:
                await self._store.settle(item.label_id, ItemState.KEPT, was=ItemState.PLANNED)  # the run stops here
            elif item.state is ItemState.DONE and item.action == "merge":
                merges += 1
                await self._store.settle(item.label_id, ItemState.KEPT, was=ItemState.DONE)
            elif item.state is ItemState.DONE:
                try:
                    done = await self._give_back(item)
                except _Retry:
                    failed += 1
                    continue
                restored += done
                changed += not done
                await self._store.settle(item.label_id, ItemState.KEPT, was=ItemState.DONE)
        await self._store.complete()
        if failed == 0:
            await self._store.close_restore(request_id)
            await self._notify(
                f"Restore is done: {restored} renamed back, {merges} merges stay as they are (the mail stays on the "
                f"existing label), {changed} left alone because they changed."
            )
        return dataclasses.replace(result, restored=restored, kept=changed, merges_left=merges, failed=failed)

    async def _give_back(self, item: StoredItem) -> bool:
        """Rename one label back by id; False when it changed since (it is left alone)."""
        labels = await asyncio.to_thread(self._gmail.list_labels)
        current = next((label for label in labels if label.id == item.label_id), None)
        if current is None or current.name != item.new_name:
            return False
        self._gmail.set_managed(ManagedSet([ManagedLabel(item.new_name, item.label_id, Role.LEGACY)]))
        try:
            await asyncio.to_thread(self._gmail.rename_label, item.label_id, item.old_name)
        except (LabelRefused, LabelNameRejected, LabelNameTaken):
            return False
        except (GmailLabelError, HttpError) as error:
            logger.warning("label rename: a restore failed kind=%s%s", type(error).__name__, _status(error))
            raise _Retry from None
        return True

    # --- notice ------------------------------------------------------------------------------------------------

    async def _notify(self, text: str) -> None:
        """One note with counts; a failed send is logged by type and never blocks the label sync."""
        try:
            await self._chat.say(text)
        except Exception as error:
            logger.warning("label rename: the notice was not sent kind=%s", type(error).__name__)


HTTP_NOT_FOUND = 404


def _legacy(label: Label | None) -> list[ManagedLabel]:
    return [] if label is None else [ManagedLabel(label.name, label.id, Role.LEGACY)]


def _check(
    item: StoredItem, labels: Sequence[Label], archive: str, protected: frozenset[str]
) -> ItemState | tuple[Label, Label | None]:
    """The verdict before any change: a final state, or the old label and (for a merge) the target to work with."""
    current = next((label for label in labels if label.id == item.label_id), None)
    if current is None:
        return ItemState.KEPT  # deleted by hand
    if item.action == "rename" and current.name == item.new_name:
        return ItemState.DONE  # an earlier pass renamed it and crashed before it was settled
    if current.name != item.old_name:
        return ItemState.KEPT  # changed by hand since the preview (AC 26)
    target = next((x for x in labels if x.id != item.label_id and x.name.casefold() == item.new_name.casefold()), None)
    if item.action == "rename":
        return ItemState.KEPT if target is not None else (current, None)  # a taken name: not what the user saw
    if target is None or target.id == target.name or target.id in protected or target.name.casefold() == archive:
        return ItemState.KEPT  # no target any more, a system label, or the archive or Other label (by id, then by name)
    return current, target


def _count(items: Sequence[StoredItem], state: ItemState, action: str | None = None) -> int:
    return sum(1 for item in items if item.state is state and (action is None or item.action == action))


def _status(error: Exception) -> str:
    status = getattr(getattr(error, "resp", None), "status", None) or getattr(error, "status", None)
    return f" status={status}" if isinstance(status, int) else ""
