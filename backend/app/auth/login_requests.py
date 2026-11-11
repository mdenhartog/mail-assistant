"""Login request store (U-web-settings-16): persistence of the e-mailed sign-in code in ``web_auth.login_request``."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import text

from app.auth.code_hash import hash_code, verify_code
from app.auth.code_rules import attempts_exhausted, code_expired, register_wrong
from app.db import Database
from app.ids import IdSource

# The column `id` is VARCHAR(32) (migration 0008): 24 random bytes are exactly 32 URL-safe characters.
_ID_BYTES: Final = 24
# Rows are kept for an hour after the request so the hourly cap of sent codes can still be counted.
RETENTION: Final = timedelta(hours=1)
_SERIALIZE_CREATE = text("SELECT pg_advisory_xact_lock(hashtext('web_auth.login_request'))")
_REMOVE_OLD = text(
    "DELETE FROM web_auth.login_request WHERE created_at < :since AND (sent_at IS NULL OR sent_at < :since)"
)
_COUNT_OPEN_OF_OTHERS = text(
    "SELECT count(*) FROM web_auth.login_request "
    "WHERE dead_at IS NULL AND expires_at > :now AND username_key <> :username_key"
)
_KILL_LIVE = text(
    "UPDATE web_auth.login_request SET dead_at = :now WHERE username_key = :username_key AND dead_at IS NULL"
)
_INSERT = text(
    "INSERT INTO web_auth.login_request (id, username_key, code_hash, expires_at, created_at) "
    "VALUES (:id, :username_key, :code_hash, :expires_at, :created_at)"
)
_LOCK_ROW = text(
    "SELECT code_hash, created_at, attempts, dead_at FROM web_auth.login_request WHERE id = :id FOR UPDATE"
)
_READ_ROW = text("SELECT created_at, attempts, dead_at FROM web_auth.login_request WHERE id = :id")
_COUNT_WRONG = text("UPDATE web_auth.login_request SET attempts = :attempts, dead_at = :dead_at WHERE id = :id")
_CONSUME = text("UPDATE web_auth.login_request SET dead_at = :now WHERE id = :id")
_MARK_SENT = text("UPDATE web_auth.login_request SET sent_at = :now WHERE id = :id AND sent_at IS NULL")
_LAST_REQUESTED = text("SELECT max(created_at) FROM web_auth.login_request WHERE username_key = :username_key")
_SENT_SINCE = text(
    "SELECT count(*) FROM web_auth.login_request WHERE username_key = :username_key AND sent_at > :since"
)
_SENT_TIMES = text(
    "SELECT sent_at FROM web_auth.login_request "
    "WHERE username_key = :username_key AND sent_at > :since ORDER BY sent_at"
)
_PAD = text("SELECT 1")


@dataclass(frozen=True)
class LoginRequest:
    """A stored login request: its id (the ``__Host-login`` cookie value) and its times."""

    id: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class Ok:
    """The code was right; the request is now dead."""


@dataclass(frozen=True)
class Wrong:
    """The code was wrong; ``attempts_left`` more may be tried."""

    attempts_left: int


@dataclass(frozen=True)
class Dead:
    """The request is unknown, replaced, used, expired or out of attempts."""


Verdict = Ok | Wrong | Dead


class LoginRequestCapReached(Exception):  # noqa: N818  # a state, not a fault
    """Too many open login requests; nothing was written."""


class LoginRequests:
    """Store of login requests for the web role: persistence only, the rules are those of ``code_rules``."""

    def __init__(
        self, database: Database, ids: IdSource, *, hash_key: bytes, ttl: timedelta, max_attempts: int
    ) -> None:
        """Build the store.

        Args:
            database: The web role's database access.
            ids: Source of the login request ids.
            hash_key: The key of the code hash.
            ttl: How long a code is valid.
            max_attempts: Wrong attempts after which a code is dead.
        """
        self._database = database
        self._ids = ids
        self._key = hash_key
        self._ttl = ttl
        self._max_attempts = max_attempts

    async def create(self, username_key: str, code: str, now: datetime, cap: int) -> LoginRequest:
        """Replace the live request of the username by a new one, in one transaction.

        Rows older than an hour go; a request that would bring the open ones to more than ``cap`` is refused before
        anything is written. Creation is serialised so the cap holds under concurrency.

        Args:
            username_key: The keyed digest of the username (64 characters).
            code: The clear code; only its hash is stored.
            now: The request time (starts the cooldown).
            cap: The maximum number of open requests.

        Returns:
            The new request.

        Raises:
            LoginRequestCapReached: Too many open requests; nothing was written.
        """
        request_id = self._ids.token(_ID_BYTES)
        code_hash = hash_code(self._key, request_id, code).hex()
        expires_at = now + self._ttl
        async with self._database.session() as session, session.begin():
            await session.execute(_SERIALIZE_CREATE)
            await session.execute(_REMOVE_OLD, {"since": now - RETENTION})
            open_others = (
                await session.execute(_COUNT_OPEN_OF_OTHERS, {"now": now, "username_key": username_key})
            ).scalar_one()
            if open_others >= cap:
                raise LoginRequestCapReached
            await session.execute(_KILL_LIVE, {"now": now, "username_key": username_key})
            await session.execute(
                _INSERT,
                {
                    "id": request_id,
                    "username_key": username_key,
                    "code_hash": code_hash,
                    "expires_at": expires_at,
                    "created_at": now,
                },
            )
        return LoginRequest(id=request_id, created_at=now, expires_at=expires_at)

    async def check(self, request_id: str | None, code: str, now: datetime) -> Verdict:
        """Check a code: the row is locked, so two checks of one request run one after the other.

        Args:
            request_id: The id from the ``__Host-login`` cookie, or None.
            code: The code the visitor typed.
            now: The time of the check.

        Returns:
            ``Ok`` (the request is now dead), ``Wrong`` with the attempts left, or ``Dead``.
        """
        if request_id is None:
            return Dead()
        async with self._database.session() as session, session.begin():
            row = (await session.execute(_LOCK_ROW, {"id": request_id})).one_or_none()
            if (
                row is None
                or row.dead_at is not None
                or code_expired(row.created_at, now, self._ttl)
                or attempts_exhausted(row.attempts, self._max_attempts)
            ):
                return Dead()
            if verify_code(self._key, request_id, code, bytes.fromhex(row.code_hash)):
                await session.execute(_CONSUME, {"now": now, "id": request_id})
                return Ok()
            attempts, dead = register_wrong(row.attempts, self._max_attempts)
            await session.execute(
                _COUNT_WRONG, {"attempts": attempts, "dead_at": now if dead else None, "id": request_id}
            )
            return Dead() if dead else Wrong(self._max_attempts - attempts)

    async def attempts_left(self, request_id: str | None, now: datetime) -> int | None:
        """Return the attempts a live request has left, or None; nothing is counted or changed.

        Args:
            request_id: The id from the ``__Host-login`` cookie, or None.
            now: The time of the read.

        Returns:
            The wrong attempts still allowed, or None when the request is unknown, replaced, used, expired or out
            of attempts.
        """
        if request_id is None:
            return None
        async with self._database.session() as session, session.begin():
            row = (await session.execute(_READ_ROW, {"id": request_id})).one_or_none()
        if (
            row is None
            or row.dead_at is not None
            or code_expired(row.created_at, now, self._ttl)
            or attempts_exhausted(row.attempts, self._max_attempts)
        ):
            return None
        return self._max_attempts - row.attempts

    async def mark_sent(self, request_id: str, now: datetime) -> None:
        """Record that the code was sent; called only after a successful send.

        Args:
            request_id: The request.
            now: The time of the send.
        """
        async with self._database.session() as session, session.begin():
            await session.execute(_MARK_SENT, {"now": now, "id": request_id})

    async def last_requested_at(self, username_key: str) -> datetime | None:
        """Return the newest creation time of the username (every request, sent or not), or None."""
        async with self._database.session() as session, session.begin():
            return (await session.execute(_LAST_REQUESTED, {"username_key": username_key})).scalar_one()

    async def sent_in_last_hour(self, username_key: str, now: datetime) -> int:
        """Count the codes of the username that were sent less than an hour before ``now``."""
        async with self._database.session() as session, session.begin():
            result = await session.execute(_SENT_SINCE, {"username_key": username_key, "since": now - RETENTION})
            return result.scalar_one()

    async def sent_times_in_last_hour(self, username_key: str, now: datetime) -> list[datetime]:
        """Return when the codes of the username were sent, less than an hour before ``now``, oldest first."""
        async with self._database.session() as session, session.begin():
            result = await session.execute(_SENT_TIMES, {"username_key": username_key, "since": now - RETENTION})
            return list(result.scalars())

    async def pad(self) -> None:
        """Run one empty transaction, so a request for an unknown username costs as many round trips."""
        async with self._database.session() as session, session.begin():
            await session.execute(_PAD)
