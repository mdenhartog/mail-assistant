"""U-quiet-hours-12: until the runtime reads the settings table (U-quiet-hours-14) the wiring hands out the defaults."""

from __future__ import annotations

from app.wiring import DefaultPolicySource
from schedule_policy.policy import DEFAULT_POLICY


async def test_given_the_interim_wiring_when_a_snapshot_is_taken_then_it_is_the_default_policy() -> None:
    assert await DefaultPolicySource().current() == DEFAULT_POLICY
