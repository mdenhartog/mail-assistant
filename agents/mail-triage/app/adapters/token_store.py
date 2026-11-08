"""Encrypted storage of the Gmail refresh token (spec AC-25; ADR-0011).

The token is encrypted with Fernet (AES-128-CBC with HMAC-SHA256, authenticated) before it reaches the database. The
key comes from the environment, never from the database. A wrong, missing or malformed key fails closed: no partial
value is ever returned, and no error message contains the token or the key.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.dialects.postgresql import insert

from app.db.models import OAuthToken

if TYPE_CHECKING:
    from pydantic import SecretStr
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ROW_ID = 1  # a single row


class TokenKeyError(ValueError):
    """The encryption key is missing or malformed. The message never contains the key."""


class TokenDecryptError(ValueError):
    """The stored token cannot be decrypted with this key (wrong key or damaged data)."""


class TokenCipher:
    """Fernet encryption of one string."""

    def __init__(self, key: SecretStr) -> None:
        """Build the cipher; raise ``TokenKeyError`` for anything but a valid Fernet key."""
        try:
            self._fernet = Fernet(key.get_secret_value())
        except (ValueError, TypeError):
            raise TokenKeyError("the token encryption key is missing or not a valid Fernet key") from None

    def encrypt(self, plain: str) -> bytes:
        """Encrypt with a fresh nonce."""
        return self._fernet.encrypt(plain.encode())

    def decrypt(self, sealed: bytes) -> str:
        """Decrypt, or raise ``TokenDecryptError``."""
        try:
            return self._fernet.decrypt(sealed).decode()
        except InvalidToken:
            raise TokenDecryptError("the stored token could not be decrypted with this key") from None


class TokenStore:
    """Saves and loads the refresh token in the ``oauth_token`` table."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], cipher: TokenCipher) -> None:
        """Wire the session factory and the cipher."""
        self._sessions = sessions
        self._cipher = cipher

    async def save(self, refresh_token: str) -> None:
        """Encrypt and store the token, replacing any earlier one."""
        if not refresh_token.strip():
            raise ValueError("refusing to store an empty token")
        sealed, now = self._cipher.encrypt(refresh_token), datetime.now(UTC)
        statement = insert(OAuthToken).values(id=ROW_ID, ciphertext=sealed, updated_at=now)
        statement = statement.on_conflict_do_update(
            index_elements=["id"], set_={"ciphertext": sealed, "updated_at": now}
        )
        async with self._sessions.begin() as session:
            await session.execute(statement)

    async def load(self) -> str | None:
        """The decrypted token, or ``None`` when none is stored."""
        async with self._sessions() as session:
            row = await session.get(OAuthToken, ROW_ID)
        return None if row is None else self._cipher.decrypt(bytes(row.ciphertext))
