"""Request-code endpoint logic (U-web-settings-17, ADR-0036, ADR-0038).

A request for the configured username and one for any other username take the same steps and give the same answer:
both read the limits first, both store one login request row, and neither waits for the mail (it is sent after the
answer). The configured username gets a code and a message. Any other username gets a decoy row: the same cookie,
expiry, attempt counter and cooldown, no code and no message, so the cooldown, the hourly cap and the attempts
answer alike.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from http.cookies import SimpleCookie
from typing import Final

from fastapi import FastAPI, Request
from sqlalchemy.exc import SQLAlchemyError

from app.auth.login_requests import LoginRequestCapReached, LoginRequests
from app.auth.mask import mask_address
from app.auth.request_code_rules import origin_allowed, same_key, username_key, wait_seconds
from app.clock import Clock
from app.codes import CodeSource
from app.config import LOGIN_COOKIE_MAX_AGE_SECONDS, Settings
from app.db import DatabaseUnavailable
from app.errors import ProblemError, RateLimited
from app.mail.sender import MailError, MailSender
from app.security_events import SecurityEvents

logger = logging.getLogger(__name__)

LOGIN_COOKIE_NAME: Final = "__Host-login"


@dataclass(frozen=True)
class Delivery:
    """A message to send after the answer."""

    login_request_id: str
    code: str
    expires_at: datetime
    username_hash: str
    client: str
    request_id: str


@dataclass(frozen=True)
class Issued:
    """The answer to a code request; ``delivery`` is None when nothing is to be sent."""

    login_request_id: str
    masked_address: str
    expires_at: datetime
    resend_after_seconds: int
    delivery: Delivery | None


def login_cookie(value: str) -> str:
    """Return the ``Set-Cookie`` value of the login request cookie.

    Args:
        value: The login request id.

    Returns:
        The header value.
    """
    jar: SimpleCookie = SimpleCookie()
    jar[LOGIN_COOKIE_NAME] = value
    morsel = jar[LOGIN_COOKIE_NAME]
    morsel["httponly"] = True
    morsel["secure"] = True
    morsel["samesite"] = "Lax"
    morsel["path"] = "/"
    morsel["max-age"] = str(LOGIN_COOKIE_MAX_AGE_SECONDS)
    return morsel.OutputString()


class CodeRequests:
    """Handles a code request: limits, login request, code and the delivery after the answer."""

    def __init__(  # noqa: PLR0913  # the collaborators of one use case
        self,
        *,
        settings: Settings,
        clock: Clock,
        codes: CodeSource,
        mailer: MailSender,
        store: LoginRequests,
        events: SecurityEvents,
    ) -> None:
        """Keep the collaborators and derive the keys once."""
        self._settings = settings
        self._clock = clock
        self._codes = codes
        self._mailer = mailer
        self._store = store
        self._events = events
        self._username_hash_key = settings.username_hash_key.get_secret_value().encode("utf-8")
        self._configured = username_key(self._username_hash_key, settings.username)
        self._cooldown = timedelta(seconds=settings.resend_cooldown_seconds)
        self._ttl = timedelta(seconds=settings.code_ttl_seconds)

    async def request(self, username: str, client: str, request_id: str) -> Issued:
        """Answer a code request.

        Args:
            username: The username as typed.
            client: The client key.
            request_id: The id of this HTTP request.

        Returns:
            The answer, and the message to send after it for the configured username.

        Raises:
            RateLimited: The cooldown or the hourly cap holds; nothing was written.
        """
        now = self._clock.now()
        key = username_key(self._username_hash_key, username)
        known = same_key(key, self._configured)
        stored_last = await self._store.last_requested_at(key)
        sent = await self._store.sent_times_in_last_hour(key, now)
        wait = wait_seconds(stored_last, sent, now, self._cooldown, self._settings.codes_per_hour)
        if wait > 0:
            await self._refuse(key, client, request_id)
            raise RateLimited(wait)
        try:
            if known:
                code = self._codes.six_digits()
                created = await self._store.create(key, code, now, self._settings.open_login_request_cap)
                delivery = Delivery(created.id, code, created.expires_at, key, client, request_id)
            else:
                created = await self._store.create_decoy(key, now, self._settings.open_login_request_cap)
                delivery = None
        except LoginRequestCapReached:
            await self._refuse(key, client, request_id)
            raise RateLimited(self._settings.resend_cooldown_seconds) from None
        return self._issued(created.id, created.expires_at, delivery)

    async def deliver(self, delivery: Delivery) -> None:
        """Send the message; a failure is logged and recorded, and changes nothing the visitor sees."""
        try:
            await self._mailer.send_code(self._settings.email_address, delivery.code, delivery.expires_at)
        except MailError:
            logger.warning("mail.failed request_id=%s", delivery.request_id)
            await self._events.record("mail_failed", delivery.request_id, delivery.client, delivery.username_hash)
            return
        try:
            await self._store.mark_sent(delivery.login_request_id, self._clock.now())
        except (DatabaseUnavailable, SQLAlchemyError) as error:
            logger.error("mail.mark_sent_failed error_class=%s", type(error).__name__)

    def _issued(self, login_request_id: str, expires_at: datetime, delivery: Delivery | None) -> Issued:
        return Issued(
            login_request_id,
            mask_address(self._settings.email_address),
            expires_at,
            self._settings.resend_cooldown_seconds,
            delivery,
        )

    async def _refuse(self, key: str, client: str, request_id: str) -> None:
        await self._events.record("code_request_refused", request_id, client, key)


def require_signin_origin(request: Request) -> None:
    """Refuse a request whose ``Origin`` is not the public origin.

    Args:
        request: The request.

    Raises:
        ProblemError: 403 for a missing or different origin.
    """
    settings: Settings = request.app.state.settings
    if not origin_allowed(request.headers.get("origin"), settings.public_origin):
        raise ProblemError(403)


def attach_request_code(app: FastAPI, store: LoginRequests, events: SecurityEvents) -> None:
    """Give the app the use case behind the request-code route.

    Args:
        app: The application, with its settings, clock, codes and mailer.
        store: The login request store.
        events: The security event store.
    """
    state = app.state
    state.security_events = events
    state.code_requests = CodeRequests(
        settings=state.settings,
        clock=state.clock,
        codes=state.codes,
        mailer=state.mailer,
        store=store,
        events=events,
    )
