"""Webhooks are delivered at least once: remember recent message ids so a retry is not answered twice."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class SeenCache:
    """A bounded set of ids with a time-to-live. One instance per process; use Redis when you run several replicas."""

    def __init__(
        self, max_items: int = 10_000, ttl_seconds: float = 3600.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Keep at most ``max_items`` ids, each for ``ttl_seconds``."""
        self._items: OrderedDict[str, float] = OrderedDict()
        self._max = max_items
        self._ttl = ttl_seconds
        self._clock = clock

    def first_time(self, key: str) -> bool:
        """Return True the first time ``key`` is seen within the time-to-live, False afterwards."""
        now = self._clock()
        while self._items and next(iter(self._items.values())) <= now - self._ttl:
            self._items.popitem(last=False)
        if key in self._items:
            return False
        self._items[key] = now
        while len(self._items) > self._max:
            self._items.popitem(last=False)
        return True
