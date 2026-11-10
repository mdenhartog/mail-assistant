"""The few database operations the agent needs, written as plain functions over an async session."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import AuditLog, Draft, MailItem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

    from schedule_policy.policy import Problem, TimePolicy

LOCK_KEY = 7_265_001  # arbitrary constant: one running agent per database


def digest_of(recipient: str, subject: str, body: str) -> str:
    """SHA-256 over recipient, subject and body, each length-prefixed so field boundaries count."""
    hasher = hashlib.sha256()
    for part in (recipient, subject, body):
        data = part.encode()
        hasher.update(len(data).to_bytes(8, "big"))
        hasher.update(data)
    return hasher.hexdigest()


async def try_claim(session: AsyncSession, gmail_message_id: str, thread_id: str) -> bool:
    """Claim a mail for processing. True only for the first caller; a second claim of the same id is refused."""
    statement = (
        insert(MailItem)
        .values(gmail_message_id=gmail_message_id, thread_id=thread_id, urgent=False, created_at=datetime.now(UTC))
        .on_conflict_do_nothing(index_elements=["gmail_message_id"])
        .returning(MailItem.id)
    )
    return (await session.execute(statement)).first() is not None


async def try_lock(connection: AsyncConnection) -> bool:
    """Take the single-replica lock on this connection; False when another connection holds it."""
    return bool((await connection.execute(text("select pg_try_advisory_lock(:key)"), {"key": LOCK_KEY})).scalar_one())


async def release_lock(connection: AsyncConnection) -> None:
    """Give the lock back."""
    await connection.execute(text("select pg_advisory_unlock(:key)"), {"key": LOCK_KEY})


async def record_audit(  # noqa: PLR0913
    session: AsyncSession,
    kind: str,
    *,
    mail_item_id: int | None = None,
    ref: str | None = None,
    digest: str | None = None,
    detail: str | None = None,
    at: datetime | None = None,
) -> None:
    """Write one audit entry: ids, hashes and a short decision, never mail text."""
    session.add(
        AuditLog(
            at=at or datetime.now(UTC), kind=kind, mail_item_id=mail_item_id, ref=ref, digest=digest, detail=detail
        )
    )


async def save_draft(  # noqa: PLR0913
    session: AsyncSession,
    draft_id: str,
    *,
    alert_id: int | None,
    recipient: str | None,
    body: str,
    digest: str,
    expires_at: datetime,
) -> None:
    """Store a draft that waits for Marco's confirmation."""
    session.add(
        Draft(
            id=draft_id,
            alert_id=alert_id,
            recipient=recipient,
            body=body,
            digest=digest,
            expires_at=expires_at,
            used=False,
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()


async def consume_draft(session: AsyncSession, draft_id: str, digest: str, *, now: datetime) -> Draft | None:
    """Use a draft once: it must exist, be unused, unexpired and match the digest Marco confirmed.

    The check and the "used" mark are one atomic statement, so a replayed confirmation finds nothing.
    """
    statement = (
        update(Draft)
        .where(Draft.id == draft_id, Draft.used.is_(False), Draft.digest == digest, Draft.expires_at > now)
        .values(used=True)
        .returning(Draft.id)
    )
    if (await session.execute(statement)).first() is None:
        return None
    return (await session.execute(select(Draft).where(Draft.id == draft_id))).scalar_one()


# ---- settings port (ADR-0025) ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StoredSettings:
    """The stored schedule row: the policy plus the version and who changed it last."""

    policy: TimePolicy
    version: int
    updated_at: datetime
    updated_via: str
    updated_by: str


@dataclass(frozen=True, slots=True)
class SettingsView:
    """What the settings dialogue needs from the row: its version and whether it can be used.

    ``version`` is 0 when no row exists. ``policy`` is the stored policy, or ``None`` when there is no row or the row is
    invalid (``invalid_rules`` then names the broken rules; stored values are never kept).
    """

    version: int
    policy: TimePolicy | None
    invalid_rules: tuple[str, ...] = ()

    @property
    def invalid(self) -> bool:
        """True when a row exists but fails validation."""
        return bool(self.invalid_rules)


class VersionConflict(Exception):  # noqa: N818  # named by the contract (spec AC-29), not an "...Error"
    """The row changed since the caller read it; nothing was written."""


class PolicyRefused(Exception):  # noqa: N818  # named by the contract, not an "...Error"
    """The policy broke a rule of ``schedule_policy.validate``; it was refused before the database was touched."""

    def __init__(self, problems: list[Problem]) -> None:
        """Keep the broken rules (rule id, value given, example) for the dialogue to word."""
        super().__init__(", ".join(problem.rule for problem in problems))  # rule ids only: no values in messages
        self.problems = problems


class StoredSettingsInvalid(Exception):  # noqa: N818  # named by the contract, not an "...Error"
    """The stored row exists but breaks a rule (for example a zone the tz database no longer has).

    ``read()`` raises this instead of returning a policy nobody validated. PolicySource catches it and falls
    back to the last good values or the defaults (C-9). Only rule ids are kept: the stored values never reach a log.
    """

    def __init__(self, rules: tuple[str, ...]) -> None:
        """Keep the broken rule ids."""
        super().__init__(", ".join(rules))
        self.rules = rules


class SettingsStoreFailure(Exception):  # noqa: N818  # named by the contract, not an "...Error"
    """The database refused or lost a read or a write. Carries the error class and SQLSTATE, never parameters."""

    def __init__(self, cause_class: str, sqlstate: str | None) -> None:
        """Keep what is safe to log about the cause."""
        super().__init__(f"{cause_class} sqlstate={sqlstate}")
        self.cause_class = cause_class
        self.sqlstate = sqlstate


class NothingToUndo(Exception):  # noqa: N818  # named by the contract, not an "...Error"
    """The version asked for is the first write: it replaced nothing, so there is nothing to put back."""


class SettingsStore(Protocol):
    """Read, replace and undo the one schedule row."""

    async def read(self) -> StoredSettings | None:
        """The stored row, or None when none was ever written. Raises ``StoredSettingsInvalid`` for an invalid row."""
        ...

    async def read_for_dialogue(self) -> SettingsView:
        """The row's version and policy for the settings dialogue; an invalid row is reported, not raised."""
        ...

    async def write(self, policy: TimePolicy, expected_version: int, via: str, by: str) -> StoredSettings:
        """Replace the whole row if it is still at ``expected_version`` (0 = no row yet)."""
        ...

    async def undo(self, expected_version: int, via: str, by: str) -> StoredSettings:
        """Put back what the change to ``expected_version`` replaced, if the row is still at that version."""
        ...
