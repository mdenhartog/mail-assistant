"""Upload, preview, confirm and restore of the category list (U-label-structure-12, ADR-0058).

The file is parsed by ``category_policy`` (never here). A preview is compared with the stored list by name (NFKC and
case folding), so a category that keeps its name keeps its id. A confirm writes one new list version through the
repository, whose database triggers derive the actor, the audit record and the data for the change notice.
Nothing of the file (a name, a description, a sender) is ever put in an exception message or a log line.
"""

import asyncio
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import TYPE_CHECKING

from app.categories_models import CategoryInput, CategoryProblem, SenderItem
from app.categories_repo import CategoriesRepository, ListSettings, StoredCategory, StoredList, VersionConflict
from app.categories_write import adopted_names, build, canonical_instructions, canonical_text, is_unchanged, problems_of
from app.errors import RateLimited
from app.schemas.category_upload import UploadPreview, UploadProblem
from app.upload_preview_repo import UploadPreviewRepository
from category_policy import normalise_name
from category_policy.yaml_file import (
    FILE_RULE_TEXT,
    FileProblems,
    ParsedList,
    dump_category_file,
    parse_category_file,
)

if TYPE_CHECKING:
    from app.clock import Clock
    from app.ids import IdSource

PREVIEW_TTL = timedelta(minutes=15)
_POLICY_TEXT = "this breaks a rule of the list"


class FileRefused(Exception):  # noqa: N818  # a verdict on the input, not a fault
    """The file broke a rule; ``problems`` names each one with its line and field (never a value)."""

    def __init__(self, problems: list[UploadProblem]) -> None:
        """Keep the problems."""
        super().__init__(len(problems))
        self.problems = problems


class Unconfirmable(Exception):  # noqa: N818  # a state of the list or the preview, not a fault
    """The preview cannot be confirmed, or the version cannot be restored: answered with 409, nothing stored."""


@dataclass(frozen=True, slots=True)
class ListPlan:
    """What a file would make of the stored list."""

    rows: list[StoredCategory]
    new_ids: frozenset[uuid.UUID]
    instructions: str
    archive_label: str
    archive_changed: bool
    added: int
    adopted: int
    changed: int
    removed: list[str]


def _file_problems(refused: FileProblems) -> list[UploadProblem]:
    return [
        UploadProblem(rule=p.rule, line=max(1, p.line), field=p.field, message=FILE_RULE_TEXT[p.rule])
        for p in refused.problems
    ]


def policy_problems(found: list[CategoryProblem]) -> list[UploadProblem]:
    """The problems found against the stored list have no line of their own: they point at line 1 and the category."""
    return [
        UploadProblem(
            rule=p.rule,
            line=1,
            field=p.field if p.index is None else f"categories[{p.index}].{p.field}",
            message=FILE_RULE_TEXT.get(p.rule, _POLICY_TEXT),
        )
        for p in found
    ]


def parse_file(data: bytes) -> ParsedList:
    """Parse a file with the shared parser.

    Args:
        data: The raw file.

    Returns:
        The parsed list.

    Raises:
        FileRefused: Every problem of the file.
    """
    parsed = parse_category_file(data)
    if isinstance(parsed, FileProblems):
        raise FileRefused(_file_problems(parsed))
    return parsed


def _inputs(parsed: ParsedList, stored: StoredList) -> list[CategoryInput]:
    """Turn a parsed list into save inputs; a name equal to a stored one (by its comparison key) gets its id."""
    known = {normalise_name(category.name): category.id for category in stored.categories}
    return [
        CategoryInput(
            id=known.get(normalise_name(category.name)),
            name=category.name,
            description=category.description,
            kind=category.kind,
            notify=category.notify,
            senders=[SenderItem(entry=e.text, subdomains=e.subdomains) for e in category.senders],
        )
        for category in parsed.categories
    ]


def plan_of(parsed: ParsedList, stored: StoredList, new_id: Callable[[], uuid.UUID]) -> ListPlan:
    """Compare a valid file with the stored list.

    Args:
        parsed: The parsed file.
        stored: The stored list.
        new_id: Makes the id of a category that is new.

    Returns:
        The rows to store and the counts of what is added, changed and removed.

    Raises:
        FileRefused: The list breaks a rule that needs the stored list (a name equal to the current "Other" name).
    """
    items = _inputs(parsed, stored)
    instructions = canonical_instructions(parsed.general_instructions)
    # A file without the field keeps the stored name: a hand-written file must never trigger a rename.
    archive = parsed.archive_label if parsed.archive_label_given else stored.archive_label
    found = problems_of(items, instructions, archive, stored.other_label, stored)
    if found:
        raise FileRefused(policy_problems(found))
    rows, new_ids = build(items, new_id)
    before = {category.id: category for category in stored.categories}
    kept = {row.id for row in rows}
    return ListPlan(
        rows=rows,
        new_ids=new_ids,
        instructions=instructions,
        archive_label=archive,
        archive_changed=archive != stored.archive_label,
        added=len(new_ids),
        adopted=len(adopted_names(rows, stored)),
        changed=sum(1 for row in rows if row.id in before and row != before[row.id]),
        removed=[canonical_text(c.name) for c in stored.categories if c.id not in kept],
    )


class CategoryUpload:
    """The use cases of the upload routes for one mailbox."""

    def __init__(  # the collaborators of the use cases
        self,
        repository: CategoriesRepository,
        previews: UploadPreviewRepository,
        clock: "Clock",
        ids: "IdSource",
        saves_per_hour: int,
    ) -> None:
        """Keep the repositories, the clock, the id source and the hourly limit of list saves."""
        self._repository = repository
        self._previews = previews
        self._clock = clock
        self._ids = ids
        self._saves_per_hour = saves_per_hour

    async def _ready_list(self) -> StoredList:
        """Return the stored list after the hourly limit of a save is checked; refuse while there is no list."""
        recent = await self._repository.recent_saves(self._clock.now())
        if recent.saves >= self._saves_per_hour:
            raise RateLimited(recent.retry_after_seconds)
        stored = await self._repository.read()
        if stored.version == 0:
            raise Unconfirmable
        return stored

    async def preview(self, data: bytes, session_digest: str) -> UploadPreview:
        """Parse a file, compare it with the list and store the preview bound to the session, hash and version.

        Args:
            data: The raw file.
            session_digest: The digest of the uploading session.

        Returns:
            The preview with its id, the file hash and the counts.

        Raises:
            RateLimited: The hourly limit of a list save is used up.
            Unconfirmable: There is no list yet.
            FileRefused: The file breaks a rule; nothing is stored.
        """
        stored = await self._ready_list()
        # A session may keep only so many previews an hour: they are stored rows too (ADR-0058 decision 4).
        held = await self._previews.recent(session_digest, self._clock.now(), PREVIEW_TTL)
        if held.saves >= self._saves_per_hour:
            raise RateLimited(held.retry_after_seconds)
        parsed = await asyncio.to_thread(parse_file, data)  # CPU-bound: not on the event loop
        plan = plan_of(parsed, stored, self._ids.category_id)  # the ids are only counted, never stored
        # The stored content names the settled archive label, so a confirm cannot fall back to the default.
        resolved = replace(parsed, archive_label=plan.archive_label, archive_label_given=True)
        preview_id = self._ids.category_id()
        file_hash = hashlib.sha256(data).hexdigest()
        expires_at = self._clock.now() + PREVIEW_TTL
        await self._previews.add(
            preview_id,
            session_digest=session_digest,
            file_hash=file_hash,
            base_version=stored.version,
            content=dump_category_file(resolved).decode(),
            expires_at=expires_at,
        )
        return UploadPreview(
            preview_id=preview_id,
            file_hash=file_hash,
            base_version=stored.version,
            expires_at=expires_at,
            added=plan.added,
            adopted=plan.adopted,
            changed=plan.changed,
            removed=len(plan.removed),
            removed_categories=plan.removed,
            instructions_changed=plan.instructions != stored.general_instructions,
            archive_label_changed=plan.archive_changed,
        )

    async def confirm(self, preview_id: uuid.UUID, file_hash: str, session_digest: str) -> StoredList:
        """Store the previewed list as one new version when every binding of the preview still holds.

        Args:
            preview_id: The id of the preview.
            file_hash: The hash the confirm names.
            session_digest: The digest of the confirming session.

        Returns:
            The stored list after the confirm.

        Raises:
            RateLimited: The hourly limit of a list save is used up.
            Unconfirmable: Another session, a changed hash, an unknown, used or expired preview, or a changed list.
        """
        stored = await self._ready_list()
        content = await self._previews.claim(
            preview_id,
            session_digest=session_digest,
            file_hash=file_hash,
            base_version=stored.version,
            now=self._clock.now(),
        )
        if content is None:
            raise Unconfirmable
        try:
            plan = plan_of(await asyncio.to_thread(parse_file, content.encode()), stored, self._ids.category_id)
        except FileRefused:
            raise Unconfirmable from None
        if is_unchanged(plan.rows, plan.instructions, plan.archive_label, stored.other_label, stored):
            return stored
        return await self._write(
            stored, plan.rows, plan.new_ids, ListSettings(plan.instructions, plan.archive_label, stored.other_label)
        )

    async def restore_previous(self, version: int) -> StoredList:
        """Store a new version equal to the one before the current version.

        Args:
            version: The version the user sees as the current one.

        Returns:
            The stored list after the restore.

        Raises:
            RateLimited: The hourly limit of a list save is used up.
            Unconfirmable: The list is not at ``version``, or the previous version does not exist (any more).
        """
        stored = await self._ready_list()
        if stored.version != version:
            raise Unconfirmable
        previous = await self._repository.read_version(version - 1)
        if previous is None:
            raise Unconfirmable
        if is_unchanged(
            list(previous.categories), previous.general_instructions, previous.archive_label, stored.other_label, stored
        ):
            return stored
        settings = ListSettings(previous.general_instructions, previous.archive_label, stored.other_label)
        return await self._write(stored, list(previous.categories), frozenset(), settings)

    async def _write(
        self,
        stored: StoredList,
        rows: list[StoredCategory],
        new_ids: frozenset[uuid.UUID],
        settings: ListSettings,
    ) -> StoredList:
        try:
            await self._repository.add_version(stored.version, rows, new_ids, settings)
        except VersionConflict:
            raise Unconfirmable from None
        return await self._repository.read()
