"""Start-up validation of the configuration (AC-4): the backend refuses to start on a wrong one.

Errors and log lines name fields, never values.
"""

import ipaddress
import logging
import re
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import SecretStr
from sqlalchemy import text

from app.auth.expiry import IDLE
from app.auth.login_requests import LOGIN_REQUEST_RETENTION
from app.clock import Clock
from app.config import Settings
from app.db import Database, DatabaseUnavailable

logger = logging.getLogger(__name__)

PURGE_EVERY = timedelta(hours=1)
MIN_KEY_BYTES = 32
_EMAIL = re.compile(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)+")
_KEY_FIELDS = ("code_hash_key", "csrf_key", "username_hash_key")
_PURGE_LOGIN_REQUESTS = text(
    "DELETE FROM web_auth.login_request WHERE expires_at <= :now AND created_at <= :retained_since"
)
_PURGE_SESSIONS = text("DELETE FROM web_auth.session WHERE absolute_expires_at <= :now OR last_seen_at <= :idle_since")


class ConfigurationError(Exception):
    """The configuration is wrong; ``fields`` names every offending field (never a value)."""

    def __init__(self, fields: tuple[str, ...]) -> None:
        """Build the error from the offending field names."""
        super().__init__("invalid configuration: " + ", ".join(fields))
        self.fields = fields


def _secret_bytes(value: SecretStr) -> bytes:
    return value.get_secret_value().encode("utf-8")


def _smtp_problems(settings: Settings) -> Iterator[str]:
    if not settings.smtp_host.strip():
        yield "smtp_host"
    if settings.smtp_port is None or not 0 < settings.smtp_port < 65536:  # noqa: PLR2004
        yield "smtp_port"
    if _EMAIL.fullmatch(settings.smtp_from) is None:
        yield "smtp_from"
    if not settings.smtp_user:
        yield "smtp_user"
    if not settings.smtp_password.get_secret_value():
        yield "smtp_password"
    if not settings.smtp_starttls:
        yield "smtp_starttls"


def _text_problems(settings: Settings) -> Iterator[str]:
    if not settings.username.strip():
        yield "username"
    if _EMAIL.fullmatch(settings.email_address) is None:
        yield "email_address"
    yield from _smtp_problems(settings)
    origin = urlsplit(settings.public_origin)
    if origin.scheme != "https" or not origin.hostname:
        yield "public_origin"


def _key_problems(settings: Settings) -> Iterator[str]:
    keys = {name: _secret_bytes(getattr(settings, name)) for name in _KEY_FIELDS}
    for name, key in keys.items():
        if len(key) < MIN_KEY_BYTES:
            yield name
    names = list(keys)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            if keys[first] == keys[second]:
                yield first
                yield second


def _database_problems(settings: Settings) -> Iterator[str]:
    # Only verify-full checks the host name as well as the certificate; production accepts nothing weaker (W-8, W-9).
    if settings.environment == "production" and settings.database_ssl != "verify-full":
        yield "database_url"


def _limit_problems(settings: Settings) -> Iterator[str]:
    # Without a trusted proxy every client shares the proxy's address and so one rate-limit bucket (RT-02, SEC-01).
    if settings.environment == "production" and not settings.trusted_proxy_cidrs:
        yield "trusted_proxy_cidrs"
    try:
        for cidr in settings.trusted_proxy_cidrs:
            ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        yield "trusted_proxy_cidrs"
    if settings.trusted_proxy_hops < 1:
        yield "trusted_proxy_hops"
    if settings.rate_limit_per_minute < 1:
        yield "rate_limit_per_minute"
    if settings.rate_window_seconds < 1:
        yield "rate_window_seconds"
    if settings.body_limit_bytes < 1:
        yield "body_limit_bytes"


def validate_startup(settings: Settings) -> None:
    """Refuse a wrong configuration, whatever the environment.

    Args:
        settings: The settings to check.

    Raises:
        ConfigurationError: Naming every offending field, never a value.
    """
    problems = (
        *_text_problems(settings),
        *_key_problems(settings),
        *_database_problems(settings),
        *_limit_problems(settings),
    )
    fields = tuple(dict.fromkeys(problems))
    if fields:
        logger.error("startup.refused fields=%s", ", ".join(fields))
        raise ConfigurationError(fields)


async def purge_expired(database: Database, clock: Clock, *, idle: timedelta = IDLE) -> None:
    """Remove the expired ``login_request`` and ``session`` rows; the time comes from the injected clock.

    A login request goes when it is expired and an hour old; a session goes when its absolute limit has passed or it
    has been idle for ``idle``.

    Args:
        database: The web role's database access.
        clock: Source of the current time.
        idle: The idle limit of a session.
    """
    now = clock.now()
    async with database.session() as session, session.begin():
        await session.execute(_PURGE_LOGIN_REQUESTS, {"now": now, "retained_since": now - LOGIN_REQUEST_RETENTION})
        await session.execute(_PURGE_SESSIONS, {"now": now, "idle_since": now - idle})


async def _database_unavailable(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(
        {"title": "Service unavailable", "status": 503}, status_code=503, media_type="application/problem+json"
    )


class _HourlyPurge:
    """Runs the purge on the first request of each hour; the start-up purge starts the first hour."""

    def __init__(self, database: Database, clock: Clock, idle: timedelta) -> None:
        self._database = database
        self._clock = clock
        self._idle = idle
        self._last: datetime | None = None

    def mark(self, now: datetime) -> None:
        """Record that a purge ran at ``now``."""
        self._last = now

    async def run_if_due(self) -> None:
        """Purge when an hour has passed since the last attempt; a failing purge is logged and never raised.

        The attempt is recorded before the purge runs, so a failing purge is not retried on every request and two
        requests at the same moment do not purge twice.
        """
        now = self._clock.now()
        if self._last is None:  # no start-up purge was recorded (the app was not started): the hour begins now
            self._last = now
            return
        if now - self._last < PURGE_EVERY:
            return
        self._last = now
        try:
            await purge_expired(self._database, self._clock, idle=self._idle)
        except Exception as error:  # the request must go on; only the error type is logged, no detail
            logger.warning("purge.failed", extra={"error_type": type(error).__name__})


def attach_database(app: FastAPI, database: Database, clock: Clock, *, idle: timedelta = IDLE) -> None:
    """Give the app its database: readiness uses it, expired rows are purged, shutdown closes the pool.

    Expired rows are purged at start-up and again on the first request of each hour. A database that cannot serve a
    request ends that request in 503 with a generic body. A purge that cannot reach the database stops neither the
    start nor a request: readiness reports it.

    Args:
        app: The application.
        database: The web role's database access.
        clock: Source of the current time.
        idle: The idle limit of a session.
    """
    app.state.database = database
    app.add_exception_handler(DatabaseUnavailable, _database_unavailable)
    hourly = _HourlyPurge(database, clock, idle)

    @app.middleware("http")
    async def purge_hourly(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        await hourly.run_if_due()
        return await call_next(request)

    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[Any]:
        try:
            await purge_expired(database, clock, idle=idle)
        except DatabaseUnavailable:
            logger.warning("startup.purge_skipped")
        hourly.mark(clock.now())
        try:
            async with previous(application) as state:
                yield state
        finally:
            await database.dispose()

    app.router.lifespan_context = lifespan
