"""Keep Gmail in step with the category list (spec C-14, C-15, AC 12, 14, 19, 25; ADR-0046, ADR-0060, ADR-0061).

The list is the label boundary. A label is *managed* when its Gmail id is the id of a category of the list, of "Other"
or of the archive label; the ids live in ``managed_label``. Each run, in this order, with Gmail effects first and the
cursor last:

1. The one-off rename plan: a mailbox without a state gets ``pending`` when an old ``Assistant/`` label exists, else
   ``done``. While the state is not ``done`` the run makes no label write at all (AC 25): it only reads, refreshes the
   counts of the labels it already knows and leaves the cursor where it is.
2. No list yet: nothing is seeded from Gmail (AC 14); "Other" and the archive label are still made.
3. Every category, "Other" and the archive label has its Gmail label: found by the stored id, else an existing label of
   the list name is adopted (any letter case, its name and mail stay), else it is made (AC 12, AC 19). A name that
   changed in the list renames the label by id: the id, the mail and the other settings stay. A rename onto the name of
   another label adopts that label instead.
4. The mail counts (by category id, "Other" under the nil id) and the names of the managed labels are refreshed for the
   api. No mail is read for a count.
5. ``list_cursor`` moves to the list version, only when nothing failed. A crash before this step repeats the run; every
   step looks at what Gmail has now, so nothing is done twice. A name that Gmail or the policy refuses is counted as
   failed and the other labels are still made.

Logs hold counts only, never label names or mail.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol

from app.adapters.gmail_resort import Label, LabelNameRejected, LabelNameTaken, LabelRefused
from app.core.managed import ManagedLabel, ManagedSet, Role
from category_policy import (
    ARCHIVE_LABEL_DEFAULT,
    OTHER_LABEL_DEFAULT,
    Category,
    validate_label_setting_name,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.db.pg_categories import CategoryRow, CurrentList

logger = logging.getLogger(__name__)

OTHER_ID = uuid.UUID(int=0)  # the nil UUID stands for "Other" in ``category_count``
_LEGACY_PREFIX = "assistant" + "/"  # the label prefix of the releases before INT-010; only the rename plan looks for it


class MigrationState(StrEnum):
    """Where the one-off rename of the old labels stands (ADR-0061); label writes wait for ``done``."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class LabelKey:
    """What a managed label stands for: a category (with its id), "Other" or the archive label."""

    kind: Literal["category", "other", "archive"]
    category_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class StoredLabel:
    """The Gmail id of a managed label and the list name it was last synced to."""

    label_id: str
    label_name: str


@dataclass(frozen=True, slots=True)
class LabelSettings:
    """The names of "Other" and the archive label in the latest list version."""

    other: str = OTHER_LABEL_DEFAULT
    archive: str = ARCHIVE_LABEL_DEFAULT


@dataclass(frozen=True, slots=True)
class SyncResult:
    """What one run did, as counts."""

    version: int
    created: int
    renamed: int
    failed: int
    held: bool = False  # the rename plan is not done: the run only read


class ManagedSink(Protocol):
    """Anything that must know the managed labels of the moment (an adapter with a guard)."""

    def set_managed(self, managed: ManagedSet) -> None:
        """Use these managed labels from now on."""
        ...


class LabelGmail(ManagedSink, Protocol):
    """The part of ``GmailResort`` the sync uses. Blocking calls; run in a thread."""

    def list_labels(self) -> list[Label]:
        """All labels."""
        ...

    def count_mail(self, label_id: str) -> int:
        """The number of mails under a label."""
        ...

    def ensure_label(self, label: ManagedLabel) -> Label:
        """The label as Gmail has it: by stored id, else adopted by name, else made."""
        ...

    def rename_label(self, label_id: str, new_name: str) -> Label:
        """Rename a managed label by id."""
        ...


class ListSyncStore(Protocol):
    """The database side of one mailbox."""

    async def current_list(self) -> CurrentList:
        """The latest list version."""
        ...

    async def cursor(self) -> int:
        """The last version whose Gmail effects are done."""
        ...

    async def migration_state(self) -> MigrationState | None:
        """The state of the rename plan; ``None`` when the mailbox has none yet."""
        ...

    async def start_migration(self, state: MigrationState) -> MigrationState:
        """Write the first state when there is none; return the state that stands (an overlapping run may be first)."""
        ...

    async def label_settings(self) -> LabelSettings:
        """The names of "Other" and the archive label in the latest list version."""
        ...

    async def managed_ids(self) -> dict[LabelKey, StoredLabel]:
        """The stored Gmail label of each managed label."""
        ...

    async def save_managed(self, key: LabelKey, label_id: str, label_name: str) -> None:
        """Remember the label of a managed key; a later call replaces the earlier one."""
        ...

    async def replace_derived(self, counts: dict[uuid.UUID, int], label_names: list[str]) -> None:
        """Replace the mail counts and the managed label names."""
        ...

    async def advance_cursor(self, version: int) -> None:
        """Record that the Gmail effects of ``version`` are done."""
        ...


@dataclass(slots=True)
class _Pass:
    """The state of one run: the labels Gmail has now, the ids already claimed, what was found and the counts."""

    by_id: dict[str, Label]
    by_name: dict[str, Label]
    claimed: set[str]
    found: dict[LabelKey, Label] = field(default_factory=dict)
    created: int = 0
    renamed: int = 0
    failed: int = 0


def _wanted(current: CurrentList, names: LabelSettings) -> list[tuple[LabelKey, ManagedLabel]]:
    """The managed labels the list and the settings want, with the names they should have."""

    def category(row: CategoryRow) -> tuple[LabelKey, ManagedLabel]:
        role = Role.EXTRA if row.kind.value == "extra" else Role.TOPIC
        return LabelKey("category", row.id), ManagedLabel(row.name.strip(), None, role)

    return [
        *(category(row) for row in current.categories),
        (LabelKey("other"), ManagedLabel(names.other, None, Role.OTHER)),
        (LabelKey("archive"), ManagedLabel(names.archive, None, Role.ARCHIVE)),
    ]


def _setting_refused(current: CurrentList, names: LabelSettings, key: LabelKey) -> bool:
    """Whether the shared policy refuses the name of "Other" or of the archive label next to these categories.

    A refused name is left out of the managed labels: no label is made or renamed for it, and the run is still done.
    """
    if key.kind == "category":
        return False
    categories = [Category(row.name, row.description, row.kind) for row in current.categories]
    if key.kind == "other":
        return bool(validate_label_setting_name(names.other, categories, names.archive, OTHER_LABEL_DEFAULT))
    return bool(validate_label_setting_name(names.archive, categories, names.other, ARCHIVE_LABEL_DEFAULT))


class ListSync:
    """One mailbox's label sync. ``gmail`` is blocking and is called through threads."""

    def __init__(self, gmail: LabelGmail, store: ListSyncStore, followers: Sequence[ManagedSink] = ()) -> None:
        """Keep the Gmail adapter, the store and the other adapters that need the managed labels of each run."""
        self._gmail = gmail
        self._store = store
        self._sinks: tuple[ManagedSink, ...] = (gmail, *followers)

    async def run(self) -> SyncResult:
        """Do one pass; see the module text for the order."""
        labels = await asyncio.to_thread(self._gmail.list_labels)
        current = await self._store.current_list()
        state = await self._migration(labels)
        names = await self._store.label_settings()
        wanted = [item for item in _wanted(current, names) if not _setting_refused(current, names, item[0])]
        stored = await self._store.managed_ids()
        self._share(ManagedSet(self._labelled(wanted, stored)))
        by_id = {label.id: label for label in labels}
        run = _Pass(by_id, {label.name.casefold(): label for label in labels}, {k.label_id for k in stored.values()})
        if state is MigrationState.DONE:
            await self._resolve(run, wanted, stored)
        else:
            run.found = {key: by_id[known.label_id] for key, known in stored.items() if known.label_id in by_id}
        counts = await self._counts(run.found)
        await self._store.replace_derived(counts, sorted({label.name for label in run.found.values()}))
        held = state is not MigrationState.DONE
        if run.failed == 0 and not held and await self._store.cursor() != current.version:
            await self._store.advance_cursor(current.version)
        logger.info(
            "list sync: version=%d created=%d renamed=%d failed=%d held=%s",
            current.version,
            run.created,
            run.renamed,
            run.failed,
            held,
        )
        return SyncResult(current.version, run.created, run.renamed, run.failed, held)

    async def _migration(self, labels: list[Label]) -> MigrationState:
        """The state of the rename plan; a mailbox without one starts ``pending`` when an old label exists."""
        state = await self._store.migration_state()
        if state is not None:
            return state
        legacy = any(label.name.casefold().startswith(_LEGACY_PREFIX) for label in labels)
        return await self._store.start_migration(MigrationState.PENDING if legacy else MigrationState.DONE)

    def _share(self, managed: ManagedSet) -> None:
        for sink in self._sinks:
            sink.set_managed(managed)

    @staticmethod
    def _labelled(
        wanted: list[tuple[LabelKey, ManagedLabel]], stored: dict[LabelKey, StoredLabel]
    ) -> list[ManagedLabel]:
        """The wanted labels with the stored ids filled in."""
        return [
            ManagedLabel(label.name, known.label_id if (known := stored.get(key)) else None, label.role)
            for key, label in wanted
        ]

    async def _resolve(
        self, run: _Pass, wanted: list[tuple[LabelKey, ManagedLabel]], stored: dict[LabelKey, StoredLabel]
    ) -> None:
        """Find, adopt, make or rename the Gmail label of each wanted managed label and remember its id."""
        for key, label in wanted:
            known = stored.get(key)
            managed = ManagedLabel(label.name, known.label_id if known else None, label.role)
            try:
                resolved = await self._one(run, managed, known)
            except (LabelNameRejected, LabelNameTaken, LabelRefused):
                logger.warning("list sync: Gmail or the policy refused the name of a label; the others go on")
                run.failed += 1
                continue
            run.found[key] = resolved
            run.claimed.add(resolved.id)
            run.by_id[resolved.id] = resolved
            run.by_name[resolved.name.casefold()] = resolved
            if known != StoredLabel(resolved.id, label.name):
                await self._store.save_managed(key, resolved.id, label.name)
        self._share(
            ManagedSet(
                ManagedLabel(label.name, run.found[key].id, label.role) if key in run.found else label
                for key, label in wanted
            )
        )

    async def _one(self, run: _Pass, label: ManagedLabel, known: StoredLabel | None) -> Label:
        """The Gmail label of one managed label: by id, adopted by name, or made; renamed when the list name moved."""
        current = run.by_id.get(known.label_id) if known else None
        if current is None:
            existing = run.by_name.get(label.name.casefold())
            if existing is not None and existing.id in run.claimed:
                raise LabelNameTaken("label_claimed")  # the label of this name is another managed label's
            made = await asyncio.to_thread(self._gmail.ensure_label, label)
            run.created += existing is None
            return made
        if known is None or known.label_name == label.name or current.name.casefold() == label.name.casefold():
            return current
        taken = run.by_name.get(label.name.casefold())
        if taken is not None and taken.id != current.id:  # the new name is a label that exists: adopt it, no rename
            if taken.id in run.claimed:
                raise LabelNameTaken("label_claimed")
            return taken
        renamed = await asyncio.to_thread(self._gmail.rename_label, current.id, label.name)
        run.renamed += 1
        return renamed

    async def _counts(self, found: dict[LabelKey, Label]) -> dict[uuid.UUID, int]:
        """The mail count of each category label and of "Other" (not of the archive label), by managed id."""
        counts: dict[uuid.UUID, int] = {}
        for key, label in found.items():
            if key.kind == "archive":
                continue
            counts[key.category_id or OTHER_ID] = await asyncio.to_thread(self._gmail.count_mail, label.id)
        return counts
