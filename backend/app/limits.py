# pure module (mutation-gated)
"""Pure rules of the request limits: fixed windows, counters per client and bucket (U-web-settings-24)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    """The answer for one request."""

    allowed: bool
    first_refusal: bool
    retry_after: int


def window_key(now: float, window_seconds: int = 60) -> int:
    """Return the window a time falls in: floor(seconds / window length)."""
    raise NotImplementedError


def retry_after(now: float, window_seconds: int = 60) -> int:
    """Return the whole seconds until the next window starts, at least 1."""
    raise NotImplementedError


class FixedWindowLimiter:
    """Counts requests per client and bucket in fixed windows and keeps the last two windows only."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        """Keep the limit and the window length."""
        raise NotImplementedError

    def hit(self, client: str, bucket: str, now: float) -> Decision:
        """Count one request and decide."""
        raise NotImplementedError

    def tracked_windows(self) -> int:
        """Return how many windows are held."""
        raise NotImplementedError

    def tracked_entries(self) -> int:
        """Return how many counters are held in all windows."""
        raise NotImplementedError
