"""Session store, cookie and lock check (U-web-settings-15): sessions in ``web_auth.session`` for the web role.

Only the SHA-256 of the session id is stored; the id itself lives in the ``__Host-session`` cookie. The expiry rules
are the pure ones of ``app.auth.expiry``. While ``web_auth.web_lock`` holds a row (ADR-0033) every lookup deletes all
sessions and fails, whatever the cookie.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from http.cookies import SimpleCookie
from typing import Final

from fastapi import FastAPI, Request
from sqlalchemy import text

from app.auth.expiry import ABSOLUTE, absolute_expired, idle_expired
from app.config import SESSION_COOKIE_MAX_AGE_SECONDS
from app.db import Database
from app.errors import ProblemError
from app.ids import IdSource
from app.security_events import SecurityEvents

COOKIE_NAME: Final = "__Host-session"
_UNKNOWN_CLIENT: Final = "unknown"  # until the client key of U-web-settings-24 exists
_LOCKED = text("SELECT 1 FROM web_auth.web_lock LIMIT 1")
_DELETE_ALL = text("DELETE FROM web_auth.session")
_INSERT = text(
    "INSERT INTO web_auth.session (id_hash, username_hash, last_seen_at, absolute_expires_at) "
    "VALUES (:id_hash, :username_hash, :now, :absolute_expires_at)"
)
_SELECT = text("SELECT username_hash, last_seen_at, absolute_expires_at FROM web_auth.session WHERE id_hash = :id_hash")
_DELETE_ONE = text("DELETE FROM web_auth.session WHERE id_hash = :id_hash")
_DELETE_RETURNING = text("DELETE FROM web_auth.session WHERE id_hash = :id_hash RETURNING username_hash")
_TOUCH = text("UPDATE web_auth.session SET last_seen_at = :now WHERE id_hash = :id_hash")


class WebLocked(Exception):  # noqa: N818  # a state, not a fault
    """The web sign-in is locked; the sessions were deleted."""


@dataclass(frozen=True)
class Session:
    """A stored session: the hash of its id, the keyed digest of the user and its times."""

    id_hash: str
    username_hash: str
    last_seen_at: datetime
    absolute_expires_at: datetime

    @property
    def created_at(self) -> datetime:
        """The creation time, derived from the absolute limit."""
        return self.absolute_expires_at - ABSOLUTE


def _hash_id(cookie_value: str) -> str:
    return hashlib.sha256(cookie_value.encode("utf-8")).hexdigest()


class SessionStore:
    """Store of sessions for the web role."""

    def __init__(self, database: Database, ids: IdSource, events: SecurityEvents) -> None:
        """Build the store.

        Args:
            database: The web role's database access.
            ids: Source of the session ids.
            events: The security event store (``session_end``).
        """
        self._database = database
        self._ids = ids
        self._events = events

    async def create(self, username_hash: str, now: datetime) -> tuple[str, Session]:
        """Create a session with a new random id; an id presented earlier is never adopted.

        Args:
            username_hash: The keyed digest of the username.
            now: The sign-in time.

        Returns:
            The cookie value (the only place the id exists) and the stored session.
        """
        cookie_value = self._ids.session_id()
        session = Session(_hash_id(cookie_value), username_hash, now, now + ABSOLUTE)
        async with self._database.session() as connection, connection.begin():
            await connection.execute(
                _INSERT,
                {
                    "id_hash": session.id_hash,
                    "username_hash": username_hash,
                    "now": now,
                    "absolute_expires_at": session.absolute_expires_at,
                },
            )
        return cookie_value, session

    async def get(self, cookie_value: str | None, now: datetime) -> Session | None:
        """Look a session up; an expired one is deleted.

        Args:
            cookie_value: The ``__Host-session`` cookie value, or None.
            now: The time of the request.

        Returns:
            The live session, or None.

        Raises:
            WebLocked: The web lock is set; all sessions were deleted.
        """
        async with self._database.session() as connection, connection.begin():
            locked = (await connection.execute(_LOCKED)).first() is not None
            if locked:
                await connection.execute(_DELETE_ALL)  # committed on leaving the block; the raise comes after it
            elif cookie_value is None:
                return None
            else:
                id_hash = _hash_id(cookie_value)
                row = (await connection.execute(_SELECT, {"id_hash": id_hash})).one_or_none()
                if row is None:
                    return None
                found = Session(id_hash, row.username_hash.strip(), row.last_seen_at, row.absolute_expires_at)
                if idle_expired(found.last_seen_at, now) or absolute_expired(found.created_at, now):
                    await connection.execute(_DELETE_ONE, {"id_hash": id_hash})
                    return None
                return found
        raise WebLocked

    async def touch(self, session: Session, now: datetime) -> None:
        """Move ``last_seen_at`` to ``now``.

        Args:
            session: The session that was used.
            now: The time of the request.
        """
        async with self._database.session() as connection, connection.begin():
            await connection.execute(_TOUCH, {"now": now, "id_hash": session.id_hash})

    async def delete(self, cookie_value: str, request_id: str, client: str) -> None:
        """Delete a session (logout) and record ``session_end`` when it existed.

        Args:
            cookie_value: The ``__Host-session`` cookie value.
            request_id: The request id, for the event.
            client: The client key, for the event.
        """
        async with self._database.session() as connection, connection.begin():
            row = (await connection.execute(_DELETE_RETURNING, {"id_hash": _hash_id(cookie_value)})).one_or_none()
        if row is not None:
            await self._events.record("session_end", request_id, client, row.username_hash.strip())


def session_cookie(value: str) -> str:
    """Build the ``Set-Cookie`` value: ``__Host-`` rules (Secure, Path=/, no Domain), HttpOnly, SameSite=Lax.

    Args:
        value: The session id.

    Returns:
        The header value.
    """
    jar: SimpleCookie = SimpleCookie()
    jar[COOKIE_NAME] = value
    morsel = jar[COOKIE_NAME]
    morsel["httponly"] = True
    morsel["secure"] = True
    morsel["samesite"] = "Lax"
    morsel["path"] = "/"
    morsel["max-age"] = str(SESSION_COOKIE_MAX_AGE_SECONDS)
    return morsel.OutputString()


def clear_session_cookie() -> str:
    """Build the ``Set-Cookie`` value that ends the session cookie in the browser (same attributes, expired now).

    Returns:
        The header value.
    """
    jar: SimpleCookie = SimpleCookie()
    jar[COOKIE_NAME] = ""
    morsel = jar[COOKIE_NAME]
    morsel["httponly"] = True
    morsel["secure"] = True
    morsel["samesite"] = "Lax"
    morsel["path"] = "/"
    morsel["max-age"] = "0"
    morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    return morsel.OutputString()


def client_key(request: Request) -> str:
    """Return the client key for events: the peer address until the client key of U-web-settings-24 exists.

    Args:
        request: The request.

    Returns:
        The address of the peer, or ``unknown``.
    """
    return request.client.host if request.client else _UNKNOWN_CLIENT


def attach_sessions(app: FastAPI, store: SessionStore, events: SecurityEvents) -> None:
    """Give the app its session store and event store.

    Args:
        app: The application.
        store: The session store.
        events: The security event store.
    """
    app.state.sessions = store
    app.state.security_events = events


async def require_session(request: Request) -> Session:
    """Return the session of the request and mark it used, or answer 401.

    Fails closed: an app without a session store refuses everything. While the web lock is set it also records a
    ``lock_refused`` event.

    Args:
        request: The request.

    Returns:
        The live session.

    Raises:
        ProblemError: 401 for no cookie, an unknown or expired session, or the web lock.
    """
    state = request.app.state
    store: SessionStore | None = getattr(state, "sessions", None)
    if store is None:
        raise ProblemError(401)
    now = state.clock.now()
    try:
        found = await store.get(request.cookies.get(COOKIE_NAME), now)
    except WebLocked:
        await state.security_events.record("lock_refused", request.state.request_id, client_key(request))
        raise ProblemError(401) from None
    if found is None:
        raise ProblemError(401)
    await store.touch(found, now)
    return found
