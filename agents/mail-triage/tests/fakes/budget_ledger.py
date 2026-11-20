"""A daily model-spend ledger with a reserve that the plan build must never touch (ADR-0021, AC-11)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.fakes.fake_clock import FakeClock


class BudgetLedger:
    """Spend per day. ``daily_total`` includes the ``reserve``; plan work may only use the part above it."""

    def __init__(self, clock: FakeClock, daily_total: int, reserve: int) -> None:
        self._clock = clock
        self._total = daily_total
        self._reserve = reserve
        self._spent: dict[str, int] = {}
        self._reserve_spent: dict[str, int] = {}

    def available(self) -> int:
        """What the plan may still spend today, above the reserve (never negative)."""
        return max(0, self._total - self._reserve - self._spent.get(self._clock.today(), 0))

    def spend(self, amount: int) -> bool:
        """Spend from the part above the reserve; False (and nothing spent) when it does not fit."""
        if amount > self.available():
            return False
        today = self._clock.today()
        self._spent[today] = self._spent.get(today, 0) + amount
        return True

    def spend_reserve(self, amount: int) -> bool:
        """Spend from the reserve (the guaranteed share of new mail); False when it does not fit."""
        today = self._clock.today()
        used = self._reserve_spent.get(today, 0)
        if used + amount > self._reserve:
            return False
        self._reserve_spent[today] = used + amount
        return True
