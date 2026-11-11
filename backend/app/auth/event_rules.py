# pure module (mutation-gated)
"""Pure rules of the security events: kinds, results, window, client class (U-web-settings-13)."""

from datetime import datetime


class UnknownEventKindError(ValueError):
    """The event kind is not one of the kinds of the table."""


def result_for(kind: str) -> str:
    """Return the result stored with a kind; refuse an unknown kind."""
    raise NotImplementedError


def event_window(now: datetime) -> int:
    """Return the one-minute window of a time: floor(epoch seconds / 60)."""
    raise NotImplementedError


def client_class(client: str) -> str:
    """Return `ipv4`, `ipv6` or `other` for a client key; the key itself is never logged."""
    raise NotImplementedError


def valid_username_hash(value: str) -> bool:
    """True for a username digest: 32 or 64 lower-case hex characters."""
    raise NotImplementedError
