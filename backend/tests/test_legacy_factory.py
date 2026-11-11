import re
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.main import create_app
from app.startup import ConfigurationError
from tests.fakes import make_app, make_settings

COMPOSE = Path(__file__).resolve().parents[2] / "compose.yaml"
SERVICE = re.compile(r"^  ([a-z0-9-]+):\n((?:(?:    .*|)\n)*)", re.MULTILINE)
VARIABLE = re.compile(r"^      (APP_[A-Z_]+): (\S+)$", re.MULTILINE)


def compose_environment(service: str) -> dict[str, str]:
    for name, body in SERVICE.findall(COMPOSE.read_text(encoding="utf-8")):
        if name == service:
            return dict(VARIABLE.findall(body))
    raise AssertionError(service)


@pytest.mark.parametrize("service", ["api", "api-dev"])
async def test_given_only_the_compose_environment_when_legacy_create_app_runs_then_health_is_served(
    service: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = compose_environment(service)
    assert environment, service
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    get_settings.cache_clear()
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/healthz")).status_code == 200
        assert (await client.get("/readyz")).status_code == 200


def test_given_production_compose_environment_when_legacy_create_app_runs_then_docs_stay_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in compose_environment("api").items():
        monkeypatch.setenv(name, value)

    get_settings.cache_clear()
    app = create_app()

    assert app.openapi_url is None


def test_given_legacy_factory_when_documented_then_it_is_marked_for_removal() -> None:
    assert create_app.__doc__ is not None
    assert "legacy" in create_app.__doc__.lower()
    assert "U-web-settings-38" in create_app.__doc__


def test_given_wrong_settings_when_build_app_runs_then_start_up_validation_refuses() -> None:
    with pytest.raises(ConfigurationError) as raised:
        make_app(make_settings(username="", smtp_starttls=False))

    assert set(raised.value.fields) == {"username", "smtp_starttls"}


def test_given_unconfigured_settings_when_build_app_runs_then_refused_in_every_environment() -> None:
    with pytest.raises(ConfigurationError):
        make_app(Settings(environment="test"))


def test_given_notice_interval_default_when_read_then_one_minute_like_the_agent_poll_interval() -> None:
    assert Settings().notice_interval_minutes == 1
