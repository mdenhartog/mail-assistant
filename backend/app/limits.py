# pure module (mutation-gated)
"""Pure rules of the request limits: fixed windows, counters per client and bucket (U-web-settings-24)."""

import math
from dataclasses import dataclass

WINDOWS_KEPT = 2


@dataclass(frozen=True)
class Decision:
    """The answer for one request: whether it may pass, whether it is the first refusal of its window, the wait."""

    allowed: bool
    first_refusal: bool
    retry_after: int


def window_key(now: float, window_seconds: int = 60) -> int:
    """Return the window a time falls in: floor(seconds / window length)."""
    return math.floor(now / window_seconds)


def retry_after(now: float, window_seconds: int = 60) -> int:
    """Return the whole seconds until the next window starts, at least 1."""
    return max(1, math.ceil((window_key(now, window_seconds) + 1) * window_seconds - now))


class FixedWindowLimiter:
    """Counts requests per client and bucket in fixed windows and keeps the last two windows only."""

    def __init__(self, limit: int, window_seconds: int, max_counters: int) -> None:
        """Keep the limit, the window length and the most counters one window may hold."""
        self._limit = limit
        self._window_seconds = window_seconds
        self._max_counters = max_counters
        self._windows: dict[int, dict[tuple[str, str], int]] = {}

    def hit(self, client: str, bucket: str, now: float) -> Decision:
        """Count one request and decide; windows older than the last two are dropped first.

        A key the window does not know yet is refused, and not stored, once the window holds the most counters; that
        refusal is never flagged as a first refusal, so a flood of new keys writes nothing and holds nothing.
        """
        window = window_key(now, self._window_seconds)
        for old in [w for w in self._windows if w <= window - WINDOWS_KEPT]:
            del self._windows[old]
        counters = self._windows.setdefault(window, {})
        key = (client, bucket)
        wait = retry_after(now, self._window_seconds)
        if key not in counters and len(counters) >= self._max_counters:
            return Decision(allowed=False, first_refusal=False, retry_after=wait)
        count = counters.get(key, 0) + 1
        counters[key] = count
        return Decision(allowed=count <= self._limit, first_refusal=count == self._limit + 1, retry_after=wait)

    def tracked_windows(self) -> int:
        """Return how many windows are held."""
        return len(self._windows)

    def tracked_entries(self) -> int:
        """Return how many counters are held in all windows."""
        return sum(len(counters) for counters in self._windows.values())
