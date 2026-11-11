# pure module (mutation-gated)
"""Pure rules of the security events: kinds, results, window, client class (U-web-settings-13)."""

import ipaddress
import re
from datetime import datetime

WINDOW_SECONDS = 60
_RESULTS = {
    "code_refused": "refused",
    "code_request_refused": "refused",
    "mail_failed": "failed",
    "session_start": "ok",
    "session_end": "ok",
    "csrf_refused": "refused",
    "rate_limited": "refused",
    "lock_refused": "refused",
}
_DIGEST = re.compile(r"[0-9a-f]{32}|[0-9a-f]{64}")


class UnknownEventKindError(ValueError):
    """The event kind is not one of the kinds of the table."""


def result_for(kind: str) -> str:
    """Return the result stored with a kind; refuse an unknown kind."""
    try:
        return _RESULTS[kind]
    except KeyError:
        raise UnknownEventKindError("unknown event kind") from None


def event_window(now: datetime) -> int:
    """Return the one-minute window of a time: floor(epoch seconds / 60)."""
    return int(now.timestamp() // WINDOW_SECONDS)


def client_class(client: str) -> str:
    """Return `ipv4`, `ipv6` or `other` for a client key; the key itself is never logged."""
    try:
        return f"ipv{ipaddress.ip_address(client).version}"
    except ValueError:
        return "other"


def valid_username_hash(value: str) -> bool:
    """True for a username digest: 32 or 64 lower-case hex characters."""
    return _DIGEST.fullmatch(value) is not None
