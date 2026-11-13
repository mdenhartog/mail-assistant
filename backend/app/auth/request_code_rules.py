# pure module (mutation-gated)
"""Rules of the request-code endpoint (U-web-settings-17, -53): origin, keys and how long a request must wait."""

import hashlib
import hmac
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.auth.code_rules import cooldown_remaining

_HOUR = timedelta(hours=1)


def origin_allowed(origin: str | None, public_origin: str) -> bool:
    """Return True only when the Origin header equals the public origin exactly."""
    return origin is not None and bool(public_origin) and origin == public_origin


def username_key(key: bytes, username: str) -> str:
    """Return the 64 lower-case hex characters of the keyed HMAC-SHA-256 of the username."""
    return hmac.new(key, username.encode("utf-8"), hashlib.sha256).hexdigest()


def same_key(first: str, second: str) -> bool:
    """Compare two username keys in constant time."""
    return hmac.compare_digest(first.encode("utf-8"), second.encode("utf-8"))


@dataclass(frozen=True)
class RequestLimits:
    """The numbers a code request is held to (ADR-0039)."""

    cooldown: timedelta  # between two requests for one username, sent or not
    codes_per_hour: int  # rows created for one username in the last hour
    live_per_username: int  # live requests of one username side by side
    open_per_client: int  # live requests of one client
    requests_per_client_per_hour: int  # rows created by one client in the last hour
    class_open_cap: int  # live requests of the same class: the owner's own, or all decoys


@dataclass(frozen=True)
class RequestFacts:
    """What the store holds about the asker, read after the requests this one replaces are dead.

    ``*_created`` are creation times of rows less than an hour old; ``*_live`` are the expiry times of live rows.
    """

    username_created: Sequence[datetime]
    username_live: Sequence[datetime]
    client_created: Sequence[datetime]
    client_live: Sequence[datetime]
    class_live: Sequence[datetime]


def client_hash(key: bytes, client: str) -> str:
    """Return the 64 lower-case hex characters of the keyed HMAC-SHA-256 of the client key.

    The label keeps it apart from a username key made with the same secret.
    """
    return hmac.new(key, b"client:" + client.encode("utf-8"), hashlib.sha256).hexdigest()


def wait_until_below(releases: Iterable[datetime], now: datetime, limit: int) -> int:
    """Return the whole seconds until fewer than ``limit`` of the held slots remain (0 when that is already so).

    Args:
        releases: When each held slot frees; a slot freed at or before ``now`` is not held.
        now: The time of the request.
        limit: How many slots may be held at once.

    Raises:
        ValueError: A time is naive.
    """
    _aware(now)
    ordered = sorted(releases)
    for release in ordered:
        _aware(release)
    # Slots freed already sort first; the one that must go for a slot to open sits at this index (a past one: no wait).
    index = len(ordered) - limit
    if index < 0:
        return 0
    return max(0, math.ceil((ordered[index] - now).total_seconds()))


def request_wait(facts: RequestFacts, now: datetime, limits: RequestLimits) -> int:
    """Return the whole seconds a new request must wait (0 when it may proceed); the longest limit wins.

    Every limit gives the time its own slot frees, so a refusal tells the truth. The hourly counts run from
    ``created_at`` for every row, so a real and a decoy username see the same wait (AC-30).

    Raises:
        ValueError: A time is naive.
    """
    newest = max(facts.username_created, default=None)
    return max(
        cooldown_remaining(newest, now, limits.cooldown),
        wait_until_below(_leaves_hour(facts.username_created), now, limits.codes_per_hour),
        wait_until_below(facts.username_live, now, limits.live_per_username),
        wait_until_below(_leaves_hour(facts.client_created), now, limits.requests_per_client_per_hour),
        wait_until_below(facts.client_live, now, limits.open_per_client),
        wait_until_below(facts.class_live, now, limits.class_open_cap),
    )


def _leaves_hour(created: Iterable[datetime]) -> list[datetime]:
    return [moment + _HOUR for moment in created]


def _aware(moment: datetime) -> None:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
