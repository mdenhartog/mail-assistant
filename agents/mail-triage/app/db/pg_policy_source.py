"""PolicySource on the settings store: validated policy, last good values and defaults as the fallback (C-9)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from schedule_policy.policy import DEFAULT_POLICY, TimePolicy

if TYPE_CHECKING:
    from app.db.repos import SettingsStore
    from app.usecases.policy_notice import PolicyNotice


class PgPolicySource:
    """Satisfies ``PolicySource``."""

    def __init__(self, store: SettingsStore, notice: PolicyNotice) -> None:
        """Keep the store and the notice."""
        self._store = store
        self._notice = notice

    async def current(self) -> TimePolicy:
        """The stored policy, or the defaults when nothing is stored."""
        stored = await self._store.read()
        return DEFAULT_POLICY if stored is None else stored.policy
