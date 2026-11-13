# pure module (mutation-gated)
"""Pure rules of the security events: kinds, results, counting, window, client class (U-web-settings-13, -54)."""

import ipaddress
import re
from datetime import datetime

WINDOW_SECONDS = 60
_RESULTS = {
    "code_refused": "refused",
    "code_invalid": "refused",
    "code_request_refused": "refused",
    "mail_failed": "failed",
    "session_start": "ok",
    "session_end": "ok",
    "csrf_refused": "refused",
    "rate_limited": "refused",
    "lock_refused": "refused",
}
_COUNTED = frozenset({"code_refused"})
_DIGEST = re.compile(r"[0-9a-f]{32}|[0-9a-f]{64}")


class UnknownEventKindError(ValueError):
    """The event kind is not one of the kinds of the table."""


def result_for(kind: str) -> str:
    """Return the result stored with a kind; refuse an unknown kind."""
    try:
        return _RESULTS[kind]
    except KeyError:
        raise UnknownEventKindError("unknown event kind") from None


def counts_repeats(kind: str) -> bool:
    """Return True when a repeat of the kind in one window is counted; False when it is dropped.

    Wrong codes against an existing login request are counted: the alert adds them up (SEC-04). ``code_invalid`` (no
    request, malformed body, dead request) is not. Every other kind is a flood answer, which must write
    no more than one row a window however many requests come.
    """
    result_for(kind)
    return kind in _COUNTED


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
