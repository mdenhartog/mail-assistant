# pure module (mutation-gated)
"""Pure rules of the request limits: fixed windows, counters per client and bucket (U-web-settings-24)."""

import math
from dataclasses import dataclass

from app.clientaddr import ipv6_prefix48

# One /48 may hold at most this share of the counters of a window: 1 in PREFIX_SHARE.
PREFIX_SHARE = 10
WINDOWS_KEPT = 2


@dataclass(frozen=True)
class Decision:
    """The answer for one request: whether it may pass, whether it is the first refusal of its window, the wait."""

    allowed: bool
    first_refusal: bool
    retry_after: int


def window_key(now: float, window_seconds: int = 60) -> int:
    """Return the window a time falls in: floor(seconds / window length)."""
    return math.floor(now) // window_seconds


def retry_after(now: float, window_seconds: int = 60) -> int:
    """Return the whole seconds until the next window starts, at least 1."""
    return math.ceil(window_seconds - now % window_seconds)


type _Key = tuple[str, str]


def surplus(held: int, bound: int) -> int:
    """Return how many of the oldest counters must go so that one more fits under the bound (0 while there is room)."""
    return max(0, held - bound + 1)


class _Window:
    """The counters of one window in the order their keys were first seen, and the same keys grouped per /48."""

    def __init__(self) -> None:
        self.counters: dict[_Key, int] = {}
        self.by_prefix: dict[str, dict[_Key, None]] = {}

    def add(self, key: _Key, prefix: str | None) -> None:
        self.counters[key] = 0
        if prefix is not None:
            self.by_prefix.setdefault(prefix, {})[key] = None

    def evict(self, key: _Key) -> None:
        del self.counters[key]
        prefix = ipv6_prefix48(key[0])
        if prefix is not None:
            group = self.by_prefix[prefix]
            del group[key]
            if not group:
                del self.by_prefix[prefix]


class FixedWindowLimiter:
    """Counts requests per client and bucket in fixed windows and keeps the last two windows only."""

    def __init__(self, limit: int, window_seconds: int, max_counters: int) -> None:
        """Keep the limit, the window length and the most counters one window may hold."""
        self._limit = limit
        self._window_seconds = window_seconds
        self._max_counters = max_counters
        self._max_per_prefix = -(-max_counters // PREFIX_SHARE)  # a tenth, rounded up: at least 1
        self._windows: dict[int, _Window] = {}

    def hit(self, client: str, bucket: str, now: float) -> Decision:
        """Count one request and decide; windows older than the last two are dropped first.

        A request is never refused because the window holds many keys (U-web-settings-64). A key the window does not
        know yet makes room instead: when its /48 holds the most counters of one /48 (a tenth of the bound), the
        oldest key of that /48 goes; when the window holds the most counters, the oldest key goes. So a flood of keys
        from one /48 only ever evicts its own counters, and no flood can refuse a client that is not over its limit.
        """
        window = window_key(now, self._window_seconds)
        for old in [w for w in self._windows if w <= window - WINDOWS_KEPT]:
            del self._windows[old]
        state = self._windows.setdefault(window, _Window())
        key = (client, bucket)
        if key not in state.counters:
            self._make_room(state, ipv6_prefix48(client))
            state.add(key, ipv6_prefix48(client))
        count = state.counters[key] + 1
        state.counters[key] = count
        return Decision(
            allowed=count <= self._limit,
            first_refusal=count == self._limit + 1,
            retry_after=retry_after(now, self._window_seconds),
        )

    def _make_room(self, state: _Window, prefix: str | None) -> None:
        if prefix is not None:
            group = state.by_prefix.get(prefix, {})
            for oldest in list(group)[: surplus(len(group), self._max_per_prefix)]:
                state.evict(oldest)
        for oldest in list(state.counters)[: surplus(len(state.counters), self._max_counters)]:
            state.evict(oldest)

    def tracked_windows(self) -> int:
        """Return how many windows are held."""
        return len(self._windows)

    def tracked_entries(self) -> int:
        """Return how many counters are held in all windows."""
        return sum(len(state.counters) for state in self._windows.values())
