"""Request-code endpoint logic (U-web-settings-17, -53, -54, ADR-0036, ADR-0038, ADR-0039).

A request for the configured username and one for any other username take the same steps and give the same answer:
both read the limits and store one login request row in one transaction, and neither waits for the mail (it is sent
after the answer). The configured username gets a code and a message. Any other username gets a decoy row: the same
cookie, expiry, attempt counter and cooldown, no code and no message, so the cooldown, the hourly cap and the
attempts answer alike.

Web lock (AC-27, SEC-08). While ``web_auth.web_lock`` is set the request takes every step and gives the answer it
would give otherwise, but no login request row is written and no message is sent: the mails stop and the lock does
not show. The lock is read in the transaction of the row, so the check cannot be missed.

Limits (ADR-0039). Decoys have their own cap of open requests and never count against the configured username; when
that class is full, a decoy request is answered like any other but stores no row, because a refusal there would be one
the owner never gets (RT2-03). Open requests and requests an hour are also capped per client (a keyed digest of the
client key is stored, never the address). A new request replaces a live one only when it carries the same login
cookie, never by client alone (a neighbour in the same /64 or behind the same NAT shares the client key, RT2-04), so
the owner's live request in one browser survives a request from another device; a username holds at most
``live_requests_per_username`` live requests, and its codes stay capped at ``codes_per_hour``, so the guessing budget
does not grow. Every refusal carries the real time until its limit frees.

Failed sends (D-11 against AC-30). The hourly caps count rows from ``created_at``, sent or not, for a real and a
decoy username alike. A decoy has no mailer, so any rule that gave a failed send back to the owner would answer the
sixth request differently for a real and an unknown username while the mailer is down, and tell anyone which
username is real. AC-30 wins: a failed send counts toward the cap. The cost is bounded: with the mailer down the owner
waits at most an hour for the oldest request to leave it, and every failure is recorded as a ``mail_failed`` event.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from sqlalchemy.exc import SQLAlchemyError

from app.auth.login_requests import Applicant, LoginRequestRefused, LoginRequests
from app.auth.mask import mask_address
from app.auth.request_code_rules import RequestLimits, client_hash, origin_allowed, same_key, username_key
from app.clock import Clock
from app.codes import CodeSource
from app.config import Settings
from app.db import DatabaseUnavailable
from app.errors import ProblemError, RateLimited
from app.mail.sender import MailError, MailSender
from app.security_events import SecurityEvents

logger = logging.getLogger(__name__)


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

    async def request(self, username: str, client: str, request_id: str, cookie: str | None) -> Issued:
        """Answer a code request.

        Args:
            username: The username as typed.
            client: The client key.
            request_id: The id of this HTTP request.
            cookie: The value of the ``__Host-login`` cookie of the request, if any.

        Returns:
            The answer, and the message to send after it for the configured username.

        Raises:
            RateLimited: A limit holds; nothing was written. It carries the real wait.
        """
        now = self._clock.now()
        key = username_key(self._username_hash_key, username)
        known = same_key(key, self._configured)
        who = Applicant(key, self._configured, client_hash(self._username_hash_key, client), cookie, known=known)
        try:
            if known:
                code = self._codes.six_digits()
                created = await self._store.create(who, code, now, self._limits(known=True))
                delivery = (
                    Delivery(created.id, code, created.expires_at, key, client, request_id) if created.stored else None
                )
            else:
                created = await self._store.create_decoy(who, now, self._limits(known=False))
                delivery = None
        except LoginRequestRefused as refused:
            await self._refuse(key, client, request_id)
            raise RateLimited(refused.wait_seconds) from None
        return self._issued(created.id, created.expires_at, delivery)

    def _limits(self, *, known: bool) -> RequestLimits:
        settings = self._settings
        return RequestLimits(
            cooldown=self._cooldown,
            codes_per_hour=settings.codes_per_hour,
            live_per_username=settings.live_requests_per_username,
            open_per_client=settings.open_login_requests_per_client,
            requests_per_client_per_hour=settings.login_requests_per_client_per_hour,
            # The owner's class is its own rows, bounded by the live number; the decoys share one cap.
            class_open_cap=settings.live_requests_per_username if known else settings.open_login_request_cap,
        )

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
