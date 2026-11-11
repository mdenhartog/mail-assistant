# pure module (mutation-gated)
"""Rules of the request-code endpoint (U-web-settings-17): origin, username key and how long a request must wait."""

import hashlib
import hmac
import math
from collections.abc import Iterable
from datetime import datetime, timedelta

from app.auth.code_rules import cooldown_remaining

_HOUR = timedelta(hours=1)


def origin_allowed(origin: str | None, public_origin: str) -> bool:
    """Return True only when the Origin header equals the public origin exactly."""
    return origin is not None and public_origin != "" and origin == public_origin


def username_key(key: bytes, username: str) -> str:
    """Return the 64 lower-case hex characters of the keyed HMAC-SHA-256 of the username."""
    return hmac.new(key, username.encode("utf-8"), hashlib.sha256).hexdigest()


def same_key(first: str, second: str) -> bool:
    """Compare two username keys in constant time."""
    return hmac.compare_digest(first.encode("utf-8"), second.encode("utf-8"))


def wait_seconds(
    last_requested_at: datetime | None, sent_times: Iterable[datetime], now: datetime, cooldown: timedelta, cap: int
) -> int:
    """Return the whole seconds a new code request must wait (0 when it may proceed).

    The cooldown counts from the last request, sent or not. The cap counts only sent codes of the last hour: when
    ``cap`` or more are in it, the request waits until enough of the oldest have left the hour. The longer wait wins.

    Raises:
        ValueError: A time is naive.
    """
    wait = cooldown_remaining(last_requested_at, now, cooldown)
    in_hour = sorted(sent for sent in sent_times if _within_hour(sent, now))
    if len(in_hour) >= cap:
        leaves_at = in_hour[len(in_hour) - cap] + _HOUR
        wait = max(wait, math.ceil((leaves_at - now).total_seconds()))
    return wait


def _within_hour(sent: datetime, now: datetime) -> bool:
    if sent.tzinfo is None or sent.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return now - sent < _HOUR
