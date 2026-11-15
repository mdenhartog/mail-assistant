"""Keep Gmail in step with the category list (INT-004, spec C-14, C-15, D11, D14, D18; ADR-0046).

Each run, in this order, with Gmail effects first and the cursor last:

1. ``Archive`` exists (created when missing, never touched otherwise, never given mail: AC-25).
2. No list yet: version 1 is seeded from the ``Assistant/`` labels that exist (AC-49).
3. Every category and "Other" has its Gmail label; a label is found by the id kept in ``category_label``, then by
   name, then made. A name-only change renames the label by id: no plan, no model call, no mail touched (AC-40).
4. The mail counts and the names of all ``Assistant/`` labels are refreshed for the api, so a label that is not on
   the list shows as an older category and its mail keeps it (AC-53). No label is ever deleted (D18).
5. ``list_cursor`` moves to the list version, only when nothing failed. A crash before this step repeats the run;
   every step looks at what Gmail has now, so nothing is done twice.

Logs hold counts only, never label names or mail.
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.adapters.gmail_resort import ARCHIVE, LABEL_PREFIX, OTHER_LABEL, Label, LabelNameTaken, is_category_label

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.db.pg_categories import CurrentList

logger = logging.getLogger(__name__)

NAME_MAX = 40  # as category-policy
MAX_CATEGORIES = 50  # as category-policy
OTHER_ID = uuid.UUID(int=0)  # the nil UUID stands for "Other" in ``category_count``
_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf"})


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
    """Category names for list version 1: the one-level ``Assistant/`` labels that fit the name rules, sorted."""
    found: dict[str, str] = {}
    for label in sorted(labels, key=lambda item: item.name):
        name = label.name[len(LABEL_PREFIX) :]
        fits = (
            is_category_label(label.name)
            and name == name.strip()
            and len(name) <= NAME_MAX
            and not any(unicodedata.category(char) in _FORBIDDEN_CATEGORIES for char in name)
        )
        if fits:
            found.setdefault(unicodedata.normalize("NFKC", name).casefold(), name)
    return tuple(found.values())[:MAX_CATEGORIES]


class ListSync:
    """One mailbox's label sync. ``gmail`` is blocking and is called through threads."""

    def __init__(self, gmail: LabelGmail, store: ListSyncStore) -> None:
        """Keep the Gmail adapter and the store."""
        self._gmail = gmail
        self._store = store

    async def run(self) -> SyncResult:
        """Do one pass; see the module text for the order."""
        labels = await asyncio.to_thread(self._gmail.list_labels)
        by_name = {label.name.casefold(): label for label in labels}
        by_id = {label.id: label for label in labels}
        await self._ensure_archive(by_name, by_id)
        current = await self._store.current_list()
        seeded = current.version == 0
        if seeded:
            current = await self._store.seed(seed_names(labels))
        stored = await self._store.stored_labels()
        created = renamed = failed = 0
        counts: dict[uuid.UUID, int] = {}
        wanted = [(row.id, f"{LABEL_PREFIX}{row.name}") for row in current.categories] + [(OTHER_ID, OTHER_LABEL)]
        for category_id, name in wanted:
            known = stored.get(category_id)
            label, made, renamed_now, clash = await self._ensure(name, known, by_id, by_name)
            created += made
            renamed += renamed_now
            failed += clash
            if category_id != OTHER_ID and known != StoredLabel(label.id, label.name):
                await self._store.save_label(category_id, label.id, label.name)
            counts[category_id] = await asyncio.to_thread(self._gmail.count_mail, label.id)
        names = [label.name for label in by_id.values() if label.name.startswith(LABEL_PREFIX)]
        await self._store.replace_derived(counts, names)
        if failed == 0 and await self._store.cursor() != current.version:
            await self._store.advance_cursor(current.version)
        logger.info("list sync: version=%d created=%d renamed=%d failed=%d", current.version, created, renamed, failed)
        return SyncResult(current.version, seeded, created, renamed, failed)

    async def _ensure(
        self, name: str, known: StoredLabel | None, by_id: dict[str, Label], by_name: dict[str, Label]
    ) -> tuple[Label, int, int, int]:
        """The label for ``name``: found by its stored id, then by name, else made; renamed by id when it differs.

        Returns the label and the counts of created, renamed and failed (a name another label already has).
        """
        label = (by_id.get(known.label_id) if known else None) or by_name.get(name.casefold())
        created = 1 if label is None else 0
        if label is None:
            label = await asyncio.to_thread(self._gmail.create_label, name)
        renamed = failed = 0
        if label.name != name:
            try:
                await asyncio.to_thread(self._gmail.rename_label, label.id, name)
            except LabelNameTaken:
                failed = 1
            else:
                renamed = 1
                label = Label(label.id, name)
        by_id[label.id] = label
        by_name[label.name.casefold()] = label
        return label, created, renamed, failed

    async def _ensure_archive(self, by_name: dict[str, Label], by_id: dict[str, Label]) -> None:
        """Make ``Archive`` when no top-level label of that name exists (case does not matter, C-14)."""
        if ARCHIVE.casefold() in by_name:
            return
        label = await asyncio.to_thread(self._gmail.create_label, ARCHIVE)
        by_name[label.name.casefold()] = label
        by_id[label.id] = label
