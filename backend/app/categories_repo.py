"""Read and write access to the category list as the web role (U-mail-categories-04, ADR-0042, ADR-0043).

Every query filters on the mailbox id. A list is only ever added as a new version (insert only); the actor, the channel
and the time of a version, and its audit record, are derived by the database, so nothing here names them.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta  # datetime is used as the type of a parameter at run time
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from category_policy import ARCHIVE_LABEL_DEFAULT, Kind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Row
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db import Database

OTHER_ID = uuid.UUID(int=0)  # the nil UUID stands for the built-in "Other" in ``category_count``
_WINDOW = timedelta(hours=1)
_HOUR = int(_WINDOW.total_seconds())
_UNIQUE_VIOLATION = "23505"

_VERSION = text("SELECT coalesce(max(version), 0) FROM categories.list_version WHERE mailbox_id = :mailbox")
_CATEGORIES = text(
    "SELECT id, name, description, kind, notify FROM categories.category "
    "WHERE mailbox_id = :mailbox AND version = :version ORDER BY position"
)
_SENDERS = text(
    "SELECT category_id, entry, subdomains FROM categories.category_sender "
    "WHERE mailbox_id = :mailbox AND version = :version"
)
# Only the entries of the version asked for: a count whose entry left the list is not read (a join, not a scan).
_SKIPPED = text(
    "SELECT s.entry, k.skipped FROM categories.sender_skip k "
    "JOIN categories.category_sender s ON s.mailbox_id = k.mailbox_id AND s.entry = k.entry "
    "WHERE k.mailbox_id = :mailbox AND s.version = :version"
)
_SETTINGS = text(
    "SELECT general_instructions, archive_label FROM categories.list_settings "
    "WHERE mailbox_id = :mailbox AND version = :version"
)
_HAS_VERSION = text("SELECT 1 FROM categories.list_version WHERE mailbox_id = :mailbox AND version = :version")
_COUNTS = text("SELECT category_id, mail_count FROM categories.category_count WHERE mailbox_id = :mailbox")
_LABELS = text("SELECT name FROM categories.gmail_label WHERE mailbox_id = :mailbox ORDER BY name")
_RECENT_SAVES = text(
    "SELECT count(*) AS saves, min(created_at) AS oldest FROM categories.list_version "
    "WHERE mailbox_id = :mailbox AND created_via = 'web' AND created_at > :since"
)
_INSERT_VERSION = text("INSERT INTO categories.list_version (mailbox_id, version) VALUES (:mailbox, :version)")
_INSERT_IDENTITY = text("INSERT INTO categories.category_identity (mailbox_id, id) VALUES (:mailbox, :id)")
_INSERT_CATEGORY = text(
    "INSERT INTO categories.category (mailbox_id, version, id, name, description, position, kind, notify) "
    "VALUES (:mailbox, :version, :id, :name, :description, :position, :kind, :notify)"
)
_INSERT_SENDER = text(
    "INSERT INTO categories.category_sender (mailbox_id, version, category_id, entry, is_domain, subdomains) "
    "VALUES (:mailbox, :version, :category_id, :entry, :is_domain, :subdomains)"
)
# The archive label is not the api's to change here: the new version carries the previous one's over (the default when
# that version has no settings row, as one written by an agent before it writes them).
_INSERT_SETTINGS = text(
    "INSERT INTO categories.list_settings (mailbox_id, version, general_instructions, archive_label) "
    "VALUES (:mailbox, :version, :instructions, :archive)"
)


@dataclass(frozen=True, slots=True)
class StoredSender:
    """A sender entry of a category in its stored form (lower-case A-labels)."""

    entry: str
    is_domain: bool
    subdomains: bool


@dataclass(frozen=True, slots=True)
class StoredCategory:
    """A category of the stored list; its senders are in the order of their entry."""

    id: uuid.UUID
    name: str
    description: str
    kind: Kind
    notify: bool
    senders: tuple[StoredSender, ...]


@dataclass(frozen=True, slots=True)
class StoredList:
    """The latest list of a mailbox with the derived numbers; version 0 and no categories until the seed exists."""

    version: int
    categories: tuple[StoredCategory, ...]
    general_instructions: str
    archive_label: str
    counts: dict[uuid.UUID, int]
    skipped: dict[str, int]  # per list entry as stored; an entry without a row has no key (its count is 0)
    labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecentSaves:
    """The web saves of the last hour: how many, and the seconds until the oldest one stops counting."""

    saves: int
    retry_after_seconds: int


class VersionConflict(Exception):  # noqa: N818  # a state of the list, not a fault of the caller
    """The list is not at the version the writer based its change on (or another writer got there first)."""


async def _insert_rows(session: AsyncSession, params: dict[str, Any], categories: Sequence[StoredCategory]) -> None:
    """Insert the category rows and the sender rows of one new version, one batch per table.

    A list of 100 categories with 100 senders each is 10 000 sender rows, so each table gets one statement.
    """
    category_rows = [
        {
            **params,
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "position": position,
            "kind": category.kind.value,
            "notify": category.notify,
        }
        for position, category in enumerate(categories)
    ]
    if category_rows:
        await session.execute(_INSERT_CATEGORY, category_rows)
    sender_rows = [
        {
            **params,
            "category_id": category.id,
            "entry": sender.entry,
            "is_domain": sender.is_domain,
            "subdomains": sender.subdomains,
        }
        for category in categories
        for sender in category.senders
    ]
    if sender_rows:
        await session.execute(_INSERT_SENDER, sender_rows)


async def _load(session: AsyncSession, mailbox: str, version: int) -> StoredList:
    """Read the categories, senders and settings of one version (version 0 is the empty list)."""
    versioned = {"mailbox": mailbox, "version": version}
    rows: Sequence[Row[Any]] = (await session.execute(_CATEGORIES, versioned)).all() if version else []
    sender_rows: Sequence[Row[Any]] = (await session.execute(_SENDERS, versioned)).all() if version else []
    settings = (await session.execute(_SETTINGS, versioned)).one_or_none() if version else None
    senders: dict[uuid.UUID, list[StoredSender]] = {}
    for sender in sender_rows:
        senders.setdefault(sender.category_id, []).append(
            StoredSender(sender.entry, is_domain="@" not in sender.entry, subdomains=sender.subdomains)
        )
    categories = tuple(
        StoredCategory(
            row.id,
            row.name,
            row.description,
            Kind(row.kind),
            notify=row.notify,
            senders=tuple(sorted(senders.get(row.id, []), key=lambda sender: sender.entry)),
        )
        for row in rows
    )
    instructions, archive = (
        (settings.general_instructions, settings.archive_label) if settings else ("", ARCHIVE_LABEL_DEFAULT)
    )
    return StoredList(version, categories, instructions, archive, {}, {}, ())


class CategoriesRepository:
    """Reads the list of one mailbox and adds new versions of it."""

    def __init__(self, database: Database, mailbox_id: str) -> None:
        """Keep the database access and the mailbox every query is limited to."""
        self._database = database
        self._mailbox = mailbox_id

    async def read(self) -> StoredList:
        """Return the latest version of the list with the mail counts and the Gmail label names.

        Returns:
            The list; version 0 with no categories when the agent has not written version 1.
        """
        params = {"mailbox": self._mailbox}
        async with self._database.session() as session, session.begin():
            version: int = (await session.execute(_VERSION, params)).scalar_one()
            stored = await _load(session, self._mailbox, version)
            counts = {row.category_id: row.mail_count for row in (await session.execute(_COUNTS, params))}
            skipped = (
                {row.entry: row.skipped for row in await session.execute(_SKIPPED, {**params, "version": version})}
                if version
                else {}
            )
            labels = tuple(row.name for row in (await session.execute(_LABELS, params)))
        return replace(stored, counts=counts, skipped=skipped, labels=labels)

    async def read_version(self, version: int) -> StoredList | None:
        """Return one stored version of the list without the counts and labels (they belong to the latest).

        Args:
            version: The version to read.

        Returns:
            The version, or None when it does not exist (never written, or already purged).
        """
        async with self._database.session() as session, session.begin():
            exists = (
                await session.execute(_HAS_VERSION, {"mailbox": self._mailbox, "version": version})
            ).scalar_one_or_none()
            return await _load(session, self._mailbox, version) if exists else None

    async def recent_saves(self, now: datetime) -> RecentSaves:
        """Count the versions the web saved for this mailbox in the hour before ``now`` (the limit of AC-33).

        Args:
            now: The time of the request, from the application's clock.

        Returns:
            The count and the wait until the oldest of them is an hour old (at least one second).
        """
        async with self._database.session() as session, session.begin():
            row = (await session.execute(_RECENT_SAVES, {"mailbox": self._mailbox, "since": now - _WINDOW})).one()
        if row.oldest is None:
            return RecentSaves(0, 1)
        wait = math.ceil((row.oldest + _WINDOW - now).total_seconds())
        return RecentSaves(row.saves, max(1, min(_HOUR, wait)))

    async def add_version(
        self,
        expected_version: int,
        categories: Sequence[StoredCategory],
        new_ids: frozenset[uuid.UUID],
        general_instructions: str,
    ) -> None:
        """Add ``expected_version + 1`` with the given categories in order, in one transaction.

        The version gets its category rows, one row per sender entry and one settings row (the general instructions;
        the archive label is carried over from the version it is based on).

        Args:
            expected_version: The version the change is based on; it must still be the latest.
            categories: The whole new list.
            general_instructions: The general instructions of the list, in their stored form.
            new_ids: The ids of the categories that did not exist before; their identity rows are inserted first.

        Raises:
            VersionConflict: Another version exists (or was written at the same moment); nothing was written.
            DBAPIError: The database refused the write (a check or a guard); nothing was written.
        """
        params = {"mailbox": self._mailbox, "version": expected_version + 1}
        try:
            async with self._database.session() as session, session.begin():
                latest = (await session.execute(_VERSION, {"mailbox": self._mailbox})).scalar_one()
                if latest != expected_version:
                    raise VersionConflict
                await session.execute(_INSERT_VERSION, params)
                for new_id in sorted(new_ids):
                    await session.execute(_INSERT_IDENTITY, {"mailbox": self._mailbox, "id": new_id})
                await _insert_rows(session, params, categories)
                previous = (
                    await session.execute(_SETTINGS, {"mailbox": self._mailbox, "version": expected_version})
                ).one_or_none()
                archive = previous.archive_label if previous else ARCHIVE_LABEL_DEFAULT
                await session.execute(
                    _INSERT_SETTINGS, {**params, "instructions": general_instructions, "archive": archive}
                )
        except IntegrityError as error:
            if getattr(error.orig, "sqlstate", None) == _UNIQUE_VIOLATION:  # (mailbox, version): a second writer won
                raise VersionConflict from None
            raise  # a check or a key of another table: a refusal of the database, not a conflict
