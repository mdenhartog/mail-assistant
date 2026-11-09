"""A PolicySource fake for use-case tests: it answers from a list and counts how often it is asked."""

from __future__ import annotations

from schedule_policy.policy import DEFAULT_POLICY, TimePolicy


class FakePolicySource:
    """Returns the policies in order; the last one repeats. ``calls`` shows how many snapshots were taken."""

    def __init__(self, *policies: TimePolicy) -> None:
        self._policies = list(policies) or [DEFAULT_POLICY]
        self.calls = 0

    async def current(self) -> TimePolicy:
        policy = self._policies[min(self.calls, len(self._policies) - 1)]
        self.calls += 1
        return policy

    def set(self, policy: TimePolicy) -> None:
        """A stored change: later snapshots return ``policy``."""
        self._policies = [policy]
        self.calls = 0
