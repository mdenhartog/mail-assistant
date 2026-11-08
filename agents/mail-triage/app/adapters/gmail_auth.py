"""Gmail credentials and service for the single owner (ADR-0011 scopes, guardrail-gmail).

The access token lives in memory only and is refreshed by google-auth on first use. The refresh token is read from the
encrypted token store (unit U-07) and handed in; it is never logged.
"""

from __future__ import annotations

from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
)
TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105  # nosec B105  # Google's public endpoint, not a secret


def build_credentials(refresh_token: str, client_id: str, client_secret: str) -> Credentials:
    """Credentials without an access token, so the first call refreshes it."""
    return Credentials(  # type: ignore[no-untyped-call]
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=list(SCOPES),
    )


def build_service(credentials: Credentials) -> Any:  # noqa: ANN401
    """The Gmail v1 service. Discovery caching is off so nothing is written to disk."""
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)
