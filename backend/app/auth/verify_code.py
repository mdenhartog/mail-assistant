"""Verify-code endpoint logic (U-web-settings-18, ADR-0036).

Every failure gives the same 400 with the same cookie handling; ``attemptsLeft`` is added only while the cookie names a
live login request. A right code while the web lock is set gets the answer of a dead request, so the lock is not
explained (AC-27). Only a well-formed wrong, expired or exhausting code against a live login request of the configured
username is recorded as ``code_refused``, the kind the agent counts; a guess against a decoy and every other refusal is
``code_invalid``, which is not counted (SEC2-01, SEC3-01). The visitor sees no difference. The code, the cookie value
and the username never reach an event or a log.
"""

from typing import Annotated, Final

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel

from app.auth.cookies import clear_login_cookie, session_cookie
from app.auth.digest import username_digest
from app.auth.login_requests import Dead, LoginRequests, Wrong
from app.auth.request_code_rules import normalize_username, username_key
from app.auth.return_to import safe_return_to
from app.auth.session import SessionStore, WebLocked
from app.auth.verify_code_rules import code_well_formed, login_id_well_formed, refusal_body
from app.clock import Clock
from app.config import Settings
from app.errors import PROBLEM_MEDIA_TYPE
from app.security_events import SecurityEvents

RETURN_TO_HEADER: Final = "X-Return-To"
_MAX_RETURN_TO: Final = 2048


class VerifyCodeBody(BaseModel):
    """The posted code and where the visitor wanted to go; the path is checked against an allow-list."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, alias_generator=to_camel)

    code: str
    return_to: Annotated[str | None, Field(max_length=_MAX_RETURN_TO)] = None


def _parse(raw_body: bytes) -> VerifyCodeBody | None:
    try:
        body = VerifyCodeBody.model_validate_json(raw_body)
    except ValidationError:
        return None
    return body if code_well_formed(body.code) else None


class VerifyCode:
    """Checks a posted code and signs the visitor in."""

    def __init__(
        self,
        *,
        settings: Settings,
        clock: Clock,
        logins: LoginRequests,
        sessions: SessionStore,
        events: SecurityEvents,
    ) -> None:
        """Keep the collaborators and derive the digest of the configured username once."""
        self._clock = clock
        self._logins = logins
        self._sessions = sessions
        self._events = events
        hash_key = settings.username_hash_key.get_secret_value().encode("utf-8")
        self._username_hash = username_digest(hash_key, settings.username)
        # the owner key follows the request-code rule; the audit digest above keeps the configured name as it is
        self._owner_key = username_key(hash_key, normalize_username(settings.username))

    async def verify(self, raw_body: bytes, cookie: str | None, client: str, request_id: str) -> Response:
        """Answer a code check.

        Args:
            raw_body: The request body, not yet parsed.
            cookie: The value of the ``__Host-login`` cookie, or None.
            client: The client key.
            request_id: The id of this HTTP request.

        Returns:
            204 with the session cookie, or the one generic 400.
        """
        now = self._clock.now()
        login_id = cookie if login_id_well_formed(cookie) else None
        body = _parse(raw_body)
        if body is None:  # a format error is not a guess: answered like any refusal, recorded but never counted
            left = await self._logins.attempts_left(login_id, now)
            return await self._refuse("code_invalid", left, client, request_id)
        verdict = await self._logins.check(login_id, body.code, now, self._owner_key)
        if isinstance(verdict, Wrong):
            kind = "code_refused" if verdict.existing else "code_invalid"
            return await self._refuse(kind, verdict.attempts_left, client, request_id)
        if isinstance(verdict, Dead):
            return await self._refuse("code_refused" if verdict.existing else "code_invalid", None, client, request_id)
        try:
            session_value, _ = await self._sessions.create(self._username_hash, now)
        except WebLocked:
            await self._events.record("lock_refused", request_id, client)
            return self._refusal(None)
        await self._events.record("session_start", request_id, client, self._username_hash)
        response = Response(status_code=204, headers={RETURN_TO_HEADER: safe_return_to(body.return_to)})
        response.headers.append("set-cookie", session_cookie(session_value))
        response.headers.append("set-cookie", clear_login_cookie())
        return response

    async def _refuse(self, kind: str, attempts_left: int | None, client: str, request_id: str) -> Response:
        await self._events.record(kind, request_id, client)
        return self._refusal(attempts_left)

    @staticmethod
    def _refusal(attempts_left: int | None) -> Response:
        response = JSONResponse(refusal_body(attempts_left), status_code=400, media_type=PROBLEM_MEDIA_TYPE)
        if attempts_left is None:  # nothing live is left to keep in the browser
            response.headers.append("set-cookie", clear_login_cookie())
        return response


def attach_verify_code(app: FastAPI, logins: LoginRequests, sessions: SessionStore, events: SecurityEvents) -> None:
    """Give the app the use case behind the verify-code route.

    Args:
        app: The application, with its settings and clock.
        logins: The login request store.
        sessions: The session store.
        events: The security event store.
    """
    state = app.state
    state.security_events = events
    state.verify_code = VerifyCode(
        settings=state.settings, clock=state.clock, logins=logins, sessions=sessions, events=events
    )
