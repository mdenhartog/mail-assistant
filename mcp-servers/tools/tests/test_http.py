import pytest
from starlette.testclient import TestClient

from app.server import create_app
from app.settings import Settings, SettingsError

TOKEN = "t" * 40
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
}
HEADERS: dict[str, str] = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def token_app():
    return create_app(Settings(auth_mode="token", auth_token=TOKEN, port=8000))


def test_ping_is_open_and_returns_json():
    with TestClient(token_app()) as client:
        response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "Healthy"}


@pytest.mark.parametrize("header", [None, "Bearer wrong", "Basic abc", f"Bearer {TOKEN}x"])
def test_mcp_requires_the_bearer_token(header: str | None):
    headers: dict[str, str] = HEADERS | ({"Authorization": header} if header else {})
    with TestClient(token_app()) as client:
        response = client.post("/mcp", json=INITIALIZE, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_mcp_initialize_works_with_the_token():
    with TestClient(token_app()) as client:
        response = client.post("/mcp", json=INITIALIZE, headers=HEADERS | {"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200


def test_platform_mode_leaves_authentication_to_agentcore():
    app = create_app(Settings(auth_mode="platform", auth_token="", port=8000))
    with TestClient(app) as client:
        assert client.post("/mcp", json=INITIALIZE, headers=HEADERS).status_code == 200


def test_settings_fail_closed():
    with pytest.raises(SettingsError):
        Settings.from_env({"MCP_AUTH_MODE": "token", "MCP_AUTH_TOKEN": "short"})
    with pytest.raises(SettingsError):
        Settings.from_env({"MCP_AUTH_MODE": "off"})
    with pytest.raises(SettingsError):
        Settings.from_env({"MCP_AUTH_MODE": "anything"})
    assert Settings.from_env({"MCP_AUTH_MODE": "off", "APP_ENVIRONMENT": "development"}).auth_mode == "off"
    assert Settings.from_env({"MCP_AUTH_TOKEN": TOKEN, "PORT": "9"}).port == 9
