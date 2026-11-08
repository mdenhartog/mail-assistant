"""The few database operations the agent needs, written as plain functions over an async session."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import AuditLog, Draft, MailItem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

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
