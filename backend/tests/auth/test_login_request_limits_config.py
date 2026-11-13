"""U-web-settings-53: the login request limit knobs have documented defaults and must be above 0."""

import pytest
from pydantic import ValidationError

from app.config import Settings

KNOBS = (
    "open_login_request_cap",
    "live_requests_per_username",
    "open_login_requests_per_client",
    "login_requests_per_client_per_hour",
)


def test_given_no_environment_when_settings_are_built_then_the_limits_have_their_documented_defaults() -> None:
    settings = Settings()

    assert settings.open_login_request_cap == 100  # decoys only (ADR-0039)
    assert settings.live_requests_per_username == 3
    assert settings.open_login_requests_per_client == 10
    assert settings.login_requests_per_client_per_hour == 20


@pytest.mark.parametrize("knob", KNOBS)
@pytest.mark.parametrize("value", [0, -1])
def test_given_a_knob_of_zero_or_less_when_settings_are_built_then_they_are_refused(knob: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{knob: value})  # pyright: ignore[reportArgumentType]
