"""Login request store (U-web-settings-16): persistence of the e-mailed sign-in code in ``web_auth.login_request``."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.code_hash import decoy_hash, hash_code, verify_code
from app.auth.code_rules import attempts_exhausted, code_expired, register_wrong
from app.auth.request_code_rules import RequestFacts, RequestLimits, request_wait, same_key
from app.db import Database
from app.ids import IdSource

# The column `id` is VARCHAR(32) (migration 0008): 24 random bytes are exactly 32 URL-safe characters.
_ID_BYTES: Final = 24
# Rows are kept for an hour after the request so the hourly caps can still be counted from created_at.
LOGIN_REQUEST_RETENTION: Final = timedelta(hours=1)
_SERIALIZE_CREATE = text("SELECT pg_advisory_xact_lock(hashtext('web_auth.login_request'))")
_REMOVE_OLD = text("DELETE FROM web_auth.login_request WHERE created_at < :since")
# A new request kills the live request of the username that carries its cookie, and only that one: the client alone
# never replaces, because a neighbour in the same /64 or behind the same NAT shares the client key (RT2-04).
_KILL_REPLACED = text(
    "UPDATE web_auth.login_request SET dead_at = :now "
    "WHERE username_key = :username_key AND dead_at IS NULL AND expires_at > :now "
    "AND id = :cookie"
)
_USERNAME_CREATED = text(
    "SELECT created_at FROM web_auth.login_request WHERE username_key = :username_key AND created_at > :since"
)
_USERNAME_LIVE = text(
    "SELECT expires_at FROM web_auth.login_request "
    "WHERE username_key = :username_key AND dead_at IS NULL AND expires_at > :now"
)
_CLIENT_CREATED = text(
    "SELECT created_at FROM web_auth.login_request WHERE client_hash = :client_hash AND created_at > :since"
)
_CLIENT_LIVE = text(
    "SELECT expires_at FROM web_auth.login_request "
    "WHERE client_hash = :client_hash AND dead_at IS NULL AND expires_at > :now"
)
# The class of a request: the owner's own rows, or every row that is not the owner's (the decoys).
_CLASS_LIVE = text(
    "SELECT expires_at FROM web_auth.login_request "
    "WHERE dead_at IS NULL AND expires_at > :now AND (username_key = :owner_key) = :known"
)
_INSERT = text(
    "INSERT INTO web_auth.login_request "
    "(id, username_key, client_hash, code_hash, expires_at, created_at, sent_at) "
    "VALUES (:id, :username_key, :client_hash, :code_hash, :expires_at, :created_at, :sent_at)"
)
_WEB_LOCKED = text("SELECT 1 FROM web_auth.web_lock LIMIT 1")
_LOCK_ROW = text(
    "SELECT code_hash, username_key, created_at, attempts, dead_at FROM web_auth.login_request "
    "WHERE id = :id FOR UPDATE"
)
_READ_ROW = text("SELECT created_at, attempts, dead_at FROM web_auth.login_request WHERE id = :id")
_COUNT_WRONG = text("UPDATE web_auth.login_request SET attempts = :attempts, dead_at = :dead_at WHERE id = :id")
_CONSUME = text("UPDATE web_auth.login_request SET dead_at = :now WHERE id = :id")
_MARK_SENT = text("UPDATE web_auth.login_request SET sent_at = :now WHERE id = :id AND sent_at IS NULL")


@dataclass(frozen=True)
class LoginRequest:
    """A stored login request: its id (the ``__Host-login`` cookie value) and its times."""

    id: str
    created_at: datetime
    expires_at: datetime
    stored: bool = True  # False while the web lock is set or the decoy class is full: the usual answer, no row


@dataclass(frozen=True)
class Ok:
    """The code was right; the request is now dead."""


@dataclass(frozen=True)
class Wrong:
    """The code was wrong; ``attempts_left`` more may be tried.

    ``existing`` is True when the row is the owner's: a guess the web lock counts. A guess against a decoy is not.
    """

    attempts_left: int
    existing: bool


@dataclass(frozen=True)
class Dead:
    """The request is unknown, replaced, used, expired or out of attempts.

    ``existing`` is True when the row was the owner's, still open, and this code killed it or found it expired for the
    first time: a guess against a real request, which the web lock counts (U-web-settings-63, -68). A decoy never is.
    """

    existing: bool = False


Verdict = Ok | Wrong | Dead


@dataclass(frozen=True)
class Applicant:
    """Who asks for a login request: the username, the owner, the client and the login cookie they came with."""

    username_key: str  # keyed digest of the username as typed
    owner_key: str  # keyed digest of the configured username
    client_hash: str  # keyed digest of the client key
    cookie: str | None  # the ``__Host-login`` value of the request, if any
    known: bool  # whether the username is the configured one


class LoginRequestRefused(Exception):  # noqa: N818  # a state, not a fault
    """A limit holds; nothing was written. ``wait_seconds`` is the real time until the limit frees."""

    def __init__(self, wait_seconds: int) -> None:
        """Keep the wait."""
        super().__init__(wait_seconds)
        self.wait_seconds = wait_seconds


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

    async def create(self, who: Applicant, code: str, now: datetime, limits: RequestLimits) -> LoginRequest:
        """Store the request of the configured username, in one transaction under every limit.

        Rows older than an hour go. The live request that carries the same cookie is replaced, never one that only
        shares the client; the others stay. Then the limits are read and, if one holds, nothing is kept (not even the
        replacement). Creation is serialised so the limits hold under concurrency.

        Args:
            who: The asker.
            code: The clear code; only its hash is stored.
            now: The request time (starts the cooldown).
            limits: The numbers the request is held to.

        Returns:
            The new request.

        Raises:
            LoginRequestRefused: A limit holds; nothing was written.
        """
        return await self._store(
            who, now, limits, lambda request_id: hash_code(self._key, request_id, code), sent_at=None
        )

    async def create_decoy(self, who: Applicant, now: datetime, limits: RequestLimits) -> LoginRequest:
        """Store a decoy request of an unknown username (ADR-0038): the same row, the same rules as ``create``.

        No code exists. The stored hash is one no code can match. Nothing marks the row as a decoy, and the limits
        read the same facts and run the same queries as for the configured username.

        Args:
            who: The asker.
            now: The request time (starts the cooldown).
            limits: The numbers the request is held to.

        Returns:
            The new request.

        Raises:
            LoginRequestRefused: A limit holds; nothing was written.
        """
        return await self._store(who, now, limits, lambda request_id: decoy_hash(self._key, request_id), sent_at=now)

    async def _store(
        self,
        who: Applicant,
        now: datetime,
        limits: RequestLimits,
        code_hash: Callable[[str], bytes],
        *,
        sent_at: datetime | None,
    ) -> LoginRequest:
        request_id = self._ids.token(_ID_BYTES)
        expires_at = now + self._ttl
        since = now - LOGIN_REQUEST_RETENTION
        async with self._database.session() as session, session.begin():
            await session.execute(_SERIALIZE_CREATE)
            await session.execute(_REMOVE_OLD, {"since": since})
            await session.execute(
                _KILL_REPLACED,
                {"now": now, "username_key": who.username_key, "cookie": who.cookie},
            )
            facts = RequestFacts(
                username_created=await _times(session, _USERNAME_CREATED, username_key=who.username_key, since=since),
                username_live=await _times(session, _USERNAME_LIVE, username_key=who.username_key, now=now),
                client_created=await _times(session, _CLIENT_CREATED, client_hash=who.client_hash, since=since),
                client_live=await _times(session, _CLIENT_LIVE, client_hash=who.client_hash, now=now),
                class_live=await _times(session, _CLASS_LIVE, owner_key=who.owner_key, known=who.known, now=now),
            )
            locked = (await session.execute(_WEB_LOCKED)).first() is not None
            # A full decoy class never refuses (RT2-03): the owner's class cannot be full from decoys, so a refusal
            # there would tell that the username is unknown. The decoy gets the usual answer and no row.
            invisible = not who.known and len(facts.class_live) >= limits.class_open_cap
            wait = request_wait(facts if who.known else replace(facts, class_live=()), now, limits)
            if wait > 0:
                raise LoginRequestRefused(wait)
            # Every step above and the hash below run locked or not, for a real and a decoy username alike (AC-30).
            row = {
                "id": request_id,
                "username_key": who.username_key,
                "client_hash": who.client_hash,
                "code_hash": code_hash(request_id).hex(),
                "expires_at": expires_at,
                "created_at": now,
                "sent_at": sent_at,
            }
            stored = not locked and not invisible  # the web lock or a full decoy class: answered, but no row (AC-27)
            if stored:
                await session.execute(_INSERT, row)
        return LoginRequest(id=request_id, created_at=now, expires_at=expires_at, stored=stored)

    async def check(self, request_id: str | None, code: str, now: datetime, owner_key: str) -> Verdict:
        """Check a code: the row is locked, so two checks of one request run one after the other.

        Args:
            request_id: The id from the ``__Host-login`` cookie, or None.
            code: The code the visitor typed.
            now: The time of the check.
            owner_key: The keyed digest of the configured username; only guesses against its rows are ``existing``.

        Returns:
            ``Ok`` (the request is now dead), ``Wrong`` with the attempts left, or ``Dead``. An expired request is
            killed by the check that finds it, so that check alone reports it as existing.
        """
        if request_id is None:
            return Dead()
        async with self._database.session() as session, session.begin():
            row = (await session.execute(_LOCK_ROW, {"id": request_id})).one_or_none()
            if row is None or row.dead_at is not None:
                return Dead()
            # Only a guess against a row of the owner counts for the web lock: a decoy answers alike but is not counted
            # (RT3-01). A request that is found expired or exhausted dies here, so it is counted once (RT3-04).
            existing = same_key(row.username_key, owner_key)
            if code_expired(row.created_at, now, self._ttl) or attempts_exhausted(row.attempts, self._max_attempts):
                await session.execute(_CONSUME, {"now": now, "id": request_id})
                return Dead(existing=existing)
            if verify_code(self._key, request_id, code, bytes.fromhex(row.code_hash)):
                await session.execute(_CONSUME, {"now": now, "id": request_id})
                return Ok()
            attempts, dead = register_wrong(row.attempts, self._max_attempts)
            await session.execute(
                _COUNT_WRONG, {"attempts": attempts, "dead_at": now if dead else None, "id": request_id}
            )
            return Dead(existing=existing) if dead else Wrong(self._max_attempts - attempts, existing=existing)

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


async def _times(session: AsyncSession, query: TextClause, **parameters: object) -> list[datetime]:
    return list((await session.execute(query, parameters)).scalars())
