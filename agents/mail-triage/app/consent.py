"""One-time Google consent for the owner: ``python -m app.consent`` (spec; ADR-0011; guardrail-oauth2-oidc).

Authorization-code flow with PKCE (S256) and a random ``state``, for an installed app: the redirect goes to a one-shot
server bound to 127.0.0.1. Only the three Gmail scopes of ADR-0011 are requested. The authorisation code, the client
secret and the tokens are never logged and never put into an error message; the refresh token goes straight into the
encrypted token store.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Protocol
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.db.migrate import SchemaNotReady, check_schema

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncEngine

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105  # nosec B105 - a public endpoint, not a secret
SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
)
CALLBACK_PATH = "/callback"
LOOPBACK = "127.0.0.1"
REDIRECT_PORT = 8765
WAIT_SECONDS = 300
HTTP_OK = 200
_PAGE = b"<html><body>Consent received. You can close this tab and return to the terminal.</body></html>"


class ConsentError(RuntimeError):
    """Consent failed. The message never contains a code, a secret or a token."""


async def require_schema(engine: AsyncEngine) -> None:
    """Stop unless the migrate job has brought the schema to this build's head; consent itself never migrates."""
    try:
        await check_schema(engine)
    except SchemaNotReady as error:
        raise ConsentError(f"{error}; this command does not migrate (ADR-0025)") from None


class TokenSink(Protocol):
    """Where the refresh token goes (the encrypted token store)."""

    async def save(self, refresh_token: str) -> None:
        """Store the token."""
        ...


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """The URL to open and the secrets that must match when the browser comes back."""

    url: str
    state: str
    verifier: str


def authorization_request(client_id: str, redirect_uri: str) -> AuthorizationRequest:
    """Build the consent URL with PKCE and state."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    return AuthorizationRequest(url=f"{AUTH_URL}?{urlencode(query)}", state=state, verifier=verifier)


async def exchange_code(  # noqa: PLR0913, PLR0917
    client: httpx.AsyncClient, client_id: str, client_secret: str, code: str, verifier: str, redirect_uri: str
) -> str:
    """Trade the code for a refresh token; raise ``ConsentError`` (without details) on any problem."""
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    try:
        response = await client.post(TOKEN_URL, data=form)
        token = response.json().get("refresh_token") if response.status_code == HTTP_OK else None
    except (httpx.HTTPError, ValueError, AttributeError):
        token = None
    if not isinstance(token, str) or not token:
        raise ConsentError("Google did not return a refresh token; run the consent again")
    return token


async def run_consent(  # noqa: PLR0913
    *,
    client: httpx.AsyncClient,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    store: TokenSink,
    show_url: Callable[[str], None],
    wait_for_redirect: Callable[[str], Awaitable[dict[str, str]]],
) -> None:
    """Show the URL, wait for the browser, check ``state``, exchange the code and store the token."""
    request = authorization_request(client_id, redirect_uri)
    show_url(request.url)
    params = await wait_for_redirect(request.state)
    if "error" in params:
        raise ConsentError("consent was not granted")
    code, state = params.get("code"), params.get("state", "")
    if not code or not hmac.compare_digest(state, request.state):
        raise ConsentError("the redirect did not match this consent request")
    token = await exchange_code(client, client_id, client_secret, code, request.verifier, redirect_uri)
    await store.save(token)


def receive_redirect(host: str, port: int, *, timeout: float, on_ready: Callable[[int], None]) -> dict[str, str]:
    """Serve on loopback until the callback arrives; return its query parameters. Everything else gets a 404."""
    if host != LOOPBACK:
        raise ConsentError("the redirect server may only listen on 127.0.0.1")
    received: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != CALLBACK_PATH:
                self.send_error(404)
                return
            received.update({key: values[0] for key, values in parse_qs(parsed.query).items()})
            self.send_response(HTTP_OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_PAGE)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - never log the query (it holds the code)
            return

    deadline = time.monotonic() + timeout
    with HTTPServer((host, port), Handler) as server:
        server.timeout = 0.5
        on_ready(server.server_address[1])
        while not received and time.monotonic() < deadline:
            server.handle_request()
    if not received:
        raise ConsentError("no redirect arrived in time")
    return received


async def main() -> None:  # pragma: no cover - thin shell around the tested pieces
    """Read the configuration from the environment and run the consent in this terminal."""
    import os  # noqa: PLC0415
    import webbrowser  # noqa: PLC0415

    from pydantic import SecretStr  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415

    from app.adapters.token_store import TokenCipher, TokenStore  # noqa: PLC0415

    redirect_uri = f"http://{LOOPBACK}:{REDIRECT_PORT}{CALLBACK_PATH}"
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        await require_schema(engine)  # the migrate job creates the token table; consent only checks it
    except ConsentError as error:
        await engine.dispose()
        raise SystemExit(str(error)) from None
    store = TokenStore(
        async_sessionmaker(engine, expire_on_commit=False), TokenCipher(SecretStr(os.environ["TOKEN_ENCRYPTION_KEY"]))
    )

    async def wait(_state: str) -> dict[str, str]:
        return await asyncio.to_thread(
            receive_redirect, LOOPBACK, REDIRECT_PORT, timeout=WAIT_SECONDS, on_ready=lambda _port: None
        )

    def show(url: str) -> None:
        print("Open this address in your browser and grant access:\n", url)
        webbrowser.open(url)

    async with httpx.AsyncClient(timeout=30) as client:
        await run_consent(
            client=client,
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            redirect_uri=redirect_uri,
            store=store,
            show_url=show,
            wait_for_redirect=wait,
        )
    await engine.dispose()
    print("Consent stored.")


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
