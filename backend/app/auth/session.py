"""Session store, cookie and lock check (U-web-settings-15): skeleton."""

from dataclasses import dataclass
from datetime import datetime

from fastapi import FastAPI, Request

from app.db import Database
from app.ids import IdSource
from app.security_events import SecurityEvents

COOKIE_NAME = "__Host-session"


class WebLocked(Exception):  # noqa: N818  # a state, not a fault
    """The web sign-in is locked; the sessions were deleted."""


@dataclass(frozen=True)
class Session:
    """A stored session."""

    id_hash: str
    username_hash: str
    last_seen_at: datetime
    absolute_expires_at: datetime


class SessionStore:
    """Store of sessions for the web role."""

    def __init__(self, database: Database, ids: IdSource, events: SecurityEvents) -> None:
        """Build the store."""
        raise NotImplementedError

    async def create(self, username_hash: str, now: datetime) -> tuple[str, Session]:
        """Create a session."""
        raise NotImplementedError

    async def get(self, cookie_value: str | None, now: datetime) -> Session | None:
        """Look a session up."""
        raise NotImplementedError

    async def touch(self, session: Session, now: datetime) -> None:
        """Move last_seen_at."""
        raise NotImplementedError

    async def delete(self, cookie_value: str, request_id: str, client: str) -> None:
        """Delete a session and record session_end."""
        raise NotImplementedError


def session_cookie(value: str) -> str:
    """Build the Set-Cookie header value."""
    raise NotImplementedError


def attach_sessions(app: FastAPI, store: SessionStore, events: SecurityEvents) -> None:
    """Give the app its session store."""
    raise NotImplementedError


async def require_session(request: Request) -> Session:
    """Return the session of the request or answer 401."""
    raise NotImplementedError
