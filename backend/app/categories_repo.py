"""Read and write access to the category list as the web role (U-mail-categories-04, ADR-0042, ADR-0043).

Every query filters on the mailbox id. A list is only ever added as a new version (insert only); the actor, the channel
and the time of a version, and its audit record, are derived by the database, so nothing here names them.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta  # datetime is used as the type of a parameter at run time
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Row

    from app.db import Database

OTHER_ID = uuid.UUID(int=0)  # the nil UUID stands for the built-in "Other" in ``category_count``
_WINDOW = timedelta(hours=1)
_HOUR = int(_WINDOW.total_seconds())

_VERSION = text("SELECT coalesce(max(version), 0) FROM categories.list_version WHERE mailbox_id = :mailbox")
_CATEGORIES = text(
    "SELECT id, name, description FROM categories.category "
    "WHERE mailbox_id = :mailbox AND version = :version ORDER BY position"
)
_COUNTS = text("SELECT category_id, mail_count FROM categories.category_count WHERE mailbox_id = :mailbox")
_LABELS = text("SELECT name FROM categories.gmail_label WHERE mailbox_id = :mailbox ORDER BY name")
_RECENT_SAVES = text(
    "SELECT count(*) AS saves, min(created_at) AS oldest FROM categories.list_version "
    "WHERE mailbox_id = :mailbox AND created_via = 'web' AND created_at > :since"
)
_INSERT_VERSION = text("INSERT INTO categories.list_version (mailbox_id, version) VALUES (:mailbox, :version)")
_INSERT_IDENTITY = text("INSERT INTO categories.category_identity (mailbox_id, id) VALUES (:mailbox, :id)")
_INSERT_CATEGORY = text(
    "INSERT INTO categories.category (mailbox_id, version, id, name, description, position) "
    "VALUES (:mailbox, :version, :id, :name, :description, :position)"
)


@dataclass(frozen=True, slots=True)
class StoredCategory:
    """A category of the stored list."""

    id: uuid.UUID
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class StoredList:
    """The latest list of a mailbox with the derived numbers; version 0 and no categories until the seed exists."""

    version: int
    categories: tuple[StoredCategory, ...]
    counts: dict[uuid.UUID, int]
    labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecentSaves:
    """The web saves of the last hour: how many, and the seconds until the oldest one stops counting."""

    saves: int
    retry_after_seconds: int


class VersionConflict(Exception):  # noqa: N818  # a state of the list, not a fault of the caller
    """The list is not at the version the writer based its change on (or another writer got there first)."""


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
            rows: Sequence[Row[Any]] = (
                (await session.execute(_CATEGORIES, {**params, "version": version})).all() if version else []
            )
            counts = {row.category_id: row.mail_count for row in (await session.execute(_COUNTS, params))}
            labels = tuple(row.name for row in (await session.execute(_LABELS, params)))
        categories = tuple(StoredCategory(row.id, row.name, row.description) for row in rows)
        return StoredList(version, categories, counts, labels)

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
        self, expected_version: int, categories: Sequence[StoredCategory], new_ids: frozenset[uuid.UUID]
    ) -> None:
        """Add ``expected_version + 1`` with the given categories in order, in one transaction.

        Args:
            expected_version: The version the change is based on; it must still be the latest.
            categories: The whole new list.
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
                for position, category in enumerate(categories):
                    await session.execute(
                        _INSERT_CATEGORY,
                        {
                            **params,
                            "id": category.id,
                            "name": category.name,
                            "description": category.description,
                            "position": position,
                        },
                    )
        except IntegrityError:  # the unique key on (mailbox, version): a second writer lost the race
            raise VersionConflict from None
