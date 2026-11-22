"""The api's access to ``categories.upload_preview`` (U-label-structure-12, ADR-0058 decision 3).

The web role may insert a preview and set ``used_at``; nothing else. Every query filters on the mailbox id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.db import Database

_INSERT = text(
    "INSERT INTO categories.upload_preview "
    "(mailbox_id, id, session_digest, file_hash, base_version, content, expires_at) "
    "VALUES (:mailbox, :id, :session, :hash, :base, :content, :expires_at)"
)
# One statement checks every binding and marks the preview used, so two confirms of one preview cannot both win.
_CLAIM = text(
    "UPDATE categories.upload_preview SET used_at = :now "
    "WHERE mailbox_id = :mailbox AND id = :id AND session_digest = :session AND file_hash = :hash "
    "AND base_version = :base AND used_at IS NULL AND expires_at > :now RETURNING content"
)


class UploadPreviewRepository:
    """Stores a preview and claims it once."""

    def __init__(self, database: Database, mailbox_id: str) -> None:
        """Keep the database access and the mailbox every query is limited to."""
        self._database = database
        self._mailbox = mailbox_id

    async def add(  # noqa: PLR0913  # the columns of one preview row
        self,
        preview_id: uuid.UUID,
        *,
        session_digest: str,
        file_hash: str,
        base_version: int,
        content: str,
        expires_at: datetime,
    ) -> None:
        """Insert a preview bound to a session, a file hash and a list version.

        Args:
            preview_id: The id of the preview.
            session_digest: The digest of the session that uploaded the file.
            file_hash: The SHA-256 of the file.
            base_version: The list version the preview was compared with.
            content: The normalised file content.
            expires_at: When the preview stops being valid.
        """
        params = {
            "mailbox": self._mailbox,
            "id": preview_id,
            "session": session_digest,
            "hash": file_hash,
            "base": base_version,
            "content": content,
            "expires_at": expires_at,
        }
        async with self._database.session() as session, session.begin():
            await session.execute(_INSERT, params)

    async def claim(  # every binding of the preview is one argument
        self,
        preview_id: uuid.UUID,
        *,
        session_digest: str,
        file_hash: str,
        base_version: int,
        now: datetime,
    ) -> str | None:
        """Mark the preview used when every binding holds, and return its content.

        Args:
            preview_id: The id of the preview.
            session_digest: The digest of the confirming session.
            file_hash: The hash the confirm names.
            base_version: The current list version.
            now: The time of the request.

        Returns:
            The normalised content, or None when the preview is unknown, used, expired or bound to something else.
        """
        params = {
            "mailbox": self._mailbox,
            "id": preview_id,
            "session": session_digest,
            "hash": file_hash,
            "base": base_version,
            "now": now,
        }
        async with self._database.session() as session, session.begin():
            return (await session.execute(_CLAIM, params)).scalar_one_or_none()
