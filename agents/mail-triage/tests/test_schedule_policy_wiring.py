"""The shared schedule-policy package is installed in the agent environment (U-quiet-hours-01b)."""

from app.wiring import DefaultPolicySource
from schedule_policy.policy import DEFAULT_POLICY, TimePolicy


async def test_given_no_settings_yet_when_the_wiring_asks_for_the_policy_then_it_gets_the_default() -> None:
    # Until U-quiet-hours-14 wires the stored settings, the overview works with the defaults.
    assert await DefaultPolicySource().current() == DEFAULT_POLICY


def test_default_policy_is_importable_from_the_shared_package() -> None:
    assert isinstance(DEFAULT_POLICY, TimePolicy)
