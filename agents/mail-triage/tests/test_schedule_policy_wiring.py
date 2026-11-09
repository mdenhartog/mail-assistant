"""The shared schedule-policy package is installed in the agent environment (U-quiet-hours-01b)."""

from schedule_policy.policy import DEFAULT_POLICY, TimePolicy


def test_default_policy_is_importable_from_the_shared_package() -> None:
    assert isinstance(DEFAULT_POLICY, TimePolicy)
