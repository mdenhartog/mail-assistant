"""Keep Gmail in step with the category list (INT-004, spec C-14, C-15, D11, D14, D18; ADR-0046).

Each run, in this order, with Gmail effects first and the cursor last:

1. The archive label (ADR-0059): the name comes from the list settings. The first time it is set, an existing label of
   that name is adopted, else it is made. A later change renames the label by id, once no plan is ``scheduled`` or
   ``applying``; until then the old name stays the protected one and the run is not done. It is never given mail or
   made twice (AC-25). When Gmail refuses the name, the run goes on without it.
2. No list yet: version 1 is seeded from the ``Assistant/`` labels that exist (AC-49).
3. Every category and "Other" has its Gmail label; a label is found by the id kept in ``category_label``, then by
   name, then made. A name-only change renames the label by id: no plan, no model call, no mail touched (AC-40).
4. The mail counts and the names of all ``Assistant/`` labels are refreshed for the api, so a label that is not on
   the list shows as an older category and its mail keeps it (AC-53). No label is ever deleted (D18).
5. ``list_cursor`` moves to the list version, only when nothing failed. A crash before this step repeats the run;
   every step looks at what Gmail has now, so nothing is done twice. A category label that Gmail refuses is counted as
   failed and the others are still made.

Logs hold counts only, never label names or mail.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.adapters.gmail_resort import (
    LABEL_PREFIX,
    OTHER_LABEL,
    Label,
    LabelNameRejected,
    LabelNameTaken,
    is_category_label,
)
from category_policy import MAX_CATEGORIES, normalise_name

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.core.scope import ArchiveLabel
    from app.db.pg_categories import CurrentList

logger = logging.getLogger(__name__)

OTHER_ID = uuid.UUID(int=0)  # the nil UUID stands for "Other" in ``category_count``


@dataclass(frozen=True, slots=True)
class StoredLabel:
    """The Gmail label of a category as the database remembers it."""

    label_id: str
    label_name: str


@dataclass(frozen=True, slots=True)
class SyncResult:
    """What one run did, as counts."""

    version: int
    seeded: bool
    created: int
    renamed: int
    failed: int
    waiting: bool = False  # the archive label rename waits for a plan to finish


@dataclass(frozen=True, slots=True)
class ArchiveNames:
    """The archive label name the list wants, and the one whose Gmail effects are done (``None``: the first time)."""

    wanted: str
    applied: str | None


class LabelGmail(Protocol):
    """The part of ``GmailResort`` the sync uses. Blocking calls; run in a thread."""

    def list_labels(self) -> list[Label]:
        """All labels."""
        ...

    def count_mail(self, label_id: str) -> int:
        """The number of mails under a label."""
        ...

    def create_label(self, name: str) -> Label:
        """Make a label, or return the one that exists."""
        ...

    def rename_label(self, label_id: str, new_name: str) -> None:
        """Rename a label by id."""
        ...

    def create_archive_label(self, name: str) -> Label:
        """Make the archive label, or return the one that exists."""
        ...

    def rename_archive_label(self, label_id: str, new_name: str) -> None:
        """Rename the archive label by id."""
        ...


class ListSyncStore(Protocol):
    """The database side of one mailbox."""

    async def current_list(self) -> CurrentList:
        """The latest list version."""
        ...

    async def cursor(self) -> int:
        """The last version whose Gmail effects are done."""
        ...

    async def stored_labels(self) -> dict[uuid.UUID, StoredLabel]:
        """The label of each category by category id."""
        ...

    async def archive_names(self) -> ArchiveNames:
        """The archive label name of the current list version and the one of the cursor version."""
        ...

    async def plan_in_flight(self) -> bool:
        """True while a plan is ``scheduled`` or ``applying``."""
        ...

    async def seed(self, names: tuple[str, ...]) -> CurrentList:
        """Write version 1 with these category names when no version exists yet; return the current list."""
        ...

    async def save_label(self, category_id: uuid.UUID, label_id: str, label_name: str) -> None:
        """Remember the label of a category."""
        ...

    async def replace_derived(self, counts: dict[uuid.UUID, int], label_names: list[str]) -> None:
        """Replace the mail counts and the ``Assistant/`` label names."""
        ...

    async def advance_cursor(self, version: int) -> None:
        """Record that the Gmail effects of ``version`` are done."""
        ...


def seed_names(labels: Sequence[Label]) -> tuple[str, ...]:
    """Category names for list version 1: the ``Assistant/`` labels that fit the policy name rules, sorted."""
    found: dict[str, str] = {}
    for label in sorted(labels, key=lambda item: item.name):
        if is_category_label(label.name):
            name = label.name[len(LABEL_PREFIX) :]
            found.setdefault(normalise_name(name), name)
    return tuple(found.values())[:MAX_CATEGORIES]


class ListSync:
    """One mailbox's label sync. ``gmail`` is blocking and is called through threads."""

    def __init__(self, gmail: LabelGmail, store: ListSyncStore, archive: ArchiveLabel) -> None:
        """Keep the Gmail adapter, the store and the shared archive label (ADR-0059)."""
        self._gmail = gmail
        self._store = store
        self._archive = archive

    async def run(self) -> SyncResult:
        """Do one pass; see the module text for the order."""
        labels = await asyncio.to_thread(self._gmail.list_labels)
        by_name = {label.name.casefold(): label for label in labels}
        by_id = {label.id: label for label in labels}
        failed_archive, waiting = await self._ensure_archive(by_name, by_id)
        current = await self._store.current_list()
        seeded = current.version == 0
        if seeded:
            current = await self._store.seed(seed_names(labels))
        stored = await self._store.stored_labels()
        created = renamed = 0
        failed = failed_archive
        counts: dict[uuid.UUID, int] = {}
        wanted = [(row.id, f"{LABEL_PREFIX}{row.name}") for row in current.categories] + [(OTHER_ID, OTHER_LABEL)]
        for category_id, name in wanted:
            known = stored.get(category_id)
            label, made, renamed_now, clash = await self._ensure(name, known, by_id, by_name)
            created += made
            renamed += renamed_now
            failed += clash
            if label is None:
                continue  # Gmail refused the name: this category has no label yet, the others go on
            if category_id != OTHER_ID and known != StoredLabel(label.id, label.name):
                await self._store.save_label(category_id, label.id, label.name)
            counts[category_id] = await asyncio.to_thread(self._gmail.count_mail, label.id)
        names = [label.name for label in by_id.values() if label.name.startswith(LABEL_PREFIX)]
        await self._store.replace_derived(counts, names)
        if failed == 0 and not waiting and await self._store.cursor() != current.version:
            await self._store.advance_cursor(current.version)
        logger.info("list sync: version=%d created=%d renamed=%d failed=%d", current.version, created, renamed, failed)
        return SyncResult(current.version, seeded, created, renamed, failed, waiting)

    async def _ensure(
        self, name: str, known: StoredLabel | None, by_id: dict[str, Label], by_name: dict[str, Label]
    ) -> tuple[Label | None, int, int, int]:
        """The label for ``name``: found by its stored id, then by name, else made; renamed by id when it differs.

        Returns the label and the counts of created, renamed and failed. A name that another label already has, or
        that Gmail refuses, counts as failed; when Gmail refuses to make the label there is no label (``None``).
        """
        label = (by_id.get(known.label_id) if known else None) or by_name.get(name.casefold())
        created = 1 if label is None else 0
        if label is None:
            try:
                label = await asyncio.to_thread(self._gmail.create_label, name)
            except LabelNameRejected:
                logger.warning("list sync: Gmail refused the name of a label it was asked to make")
                return None, 0, 0, 1
        renamed = failed = 0
        if label.name != name:
            try:
                await asyncio.to_thread(self._gmail.rename_label, label.id, name)
            except (LabelNameTaken, LabelNameRejected):
                failed = 1
            else:
                renamed = 1
                label = Label(label.id, name)
        by_id[label.id] = label
        by_name[label.name.casefold()] = label
        return label, created, renamed, failed

    async def _ensure_archive(self, by_name: dict[str, Label], by_id: dict[str, Label]) -> tuple[int, bool]:
        """Adopt, make or rename the archive label; return the failed count and whether a rename waits (ADR-0059).

        Matching is by name without regard to case (C-14). The shared ``ArchiveLabel`` takes the name the label has in
        Gmail, so the old name protects mail until a rename is done.
        """
        names = await self._store.archive_names()
        target = by_name.get(names.wanted.casefold())
        old = by_name.get(names.applied.casefold()) if names.applied is not None else None
        if old is not None and (target is None or target.id == old.id):
            if names.wanted in (names.applied, old.name):
                self._adopt(old, by_name, by_id)
                return 0, False
            return await self._rename(old, names.wanted, by_name, by_id)
        if old is not None:  # another label already has the new name: the old label stays the archive label
            self._adopt(old, by_name, by_id)
            logger.warning("list sync: the new archive label name is taken by another label; no rename")
            return 1, False
        if target is not None:  # the first time, or a rename that an earlier run did before it crashed
            self._adopt(target, by_name, by_id)
            return 0, False
        try:
            label = await asyncio.to_thread(self._gmail.create_archive_label, names.wanted)
        except LabelNameRejected:
            # The archive label is the user's own place for mail that must stay where it is. Without it the sync of the
            # categories goes on, and a missing archive label does not keep the run from being done.
            logger.warning("list sync: Gmail refused to make the archive label; the sync goes on without it")
            self._archive.name = names.wanted
            self._archive.label_id = None
            return 0, False
        self._adopt(label, by_name, by_id)
        return 0, False

    async def _rename(
        self, old: Label, wanted: str, by_name: dict[str, Label], by_id: dict[str, Label]
    ) -> tuple[int, bool]:
        self._adopt(old, by_name, by_id)  # the old name protects the mail until Gmail has the new one
        if await self._store.plan_in_flight():
            logger.info("list sync: the archive label rename waits for the plan to finish")
            return 0, True
        try:
            await asyncio.to_thread(self._gmail.rename_archive_label, old.id, wanted)
        except (LabelNameTaken, LabelNameRejected):
            return 1, False
        self._adopt(Label(old.id, wanted), by_name, by_id)
        return 0, False

    def _adopt(self, label: Label, by_name: dict[str, Label], by_id: dict[str, Label]) -> None:
        for known in [n for n, item in by_name.items() if item.id == label.id]:
            del by_name[known]
        by_name[label.name.casefold()] = label
        by_id[label.id] = label
        self._archive.name = label.name
        self._archive.label_id = label.id
