import boto3
import httpx
import pytest
from starlette.testclient import TestClient

from app.a2a_main import create_app as create_a2a_app
from app.agent import build_agent, build_tools
from app.main import create_app
from app.mcp_auth import SigV4, runtime_url
from app.memory import AgentPool
from app.settings import Settings, SettingsError
from tests import DEV

from .fakes import ScriptedModel

TOKEN = "t" * 40
ARN = "arn:aws:bedrock-agentcore:eu-west-1:123456789012:runtime/tools_mcp-abc123"
TOKEN_ENV = {"AGENT_AUTH_MODE": "token", "AGENT_AUTH_TOKEN": TOKEN}


def token_client() -> TestClient:
    settings = Settings.from_env(TOKEN_ENV)
    pool = AgentPool(lambda s, a: build_agent(settings, s, a, model=ScriptedModel("pong")), settings.max_sessions)
    return TestClient(create_app(settings, pool))


@pytest.mark.parametrize("header", [None, "Bearer wrong", "Basic abc", f"Bearer {TOKEN}x"])
def test_invocations_need_the_bearer_token(header: str | None):
    headers = {"Authorization": header} if header else {}
    response = token_client().post("/invocations", json={"prompt": "ping"}, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_the_right_token_is_answered_and_ping_stays_open():
    client = token_client()
    assert client.get("/ping").status_code == 200
    response = client.post("/invocations", json={"prompt": "ping"}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200
    assert response.json()["response"] == "pong"


@pytest.mark.parametrize(
    "env",
    [
        {},  # token mode is the default and needs a token
        {"AGENT_AUTH_MODE": "token", "AGENT_AUTH_TOKEN": "short"},
        {"AGENT_AUTH_MODE": "off"},  # production by default
        {"AGENT_AUTH_MODE": "anything"},
    ],
)
def test_the_agent_refuses_to_start_without_a_safe_auth_mode(env: dict[str, str]):
    with pytest.raises(SettingsError):
        Settings.from_env(env)


def test_platform_mode_leaves_authentication_to_agentcore():
    assert Settings.from_env({"AGENT_AUTH_MODE": "platform"}).auth_mode == "platform"


def test_runtime_arns_are_validated_and_turned_into_invocation_urls():
    assert Settings.from_env(DEV | {"AGENT_MCP_RUNTIME_ARNS": ARN}).mcp_runtime_arns == (ARN,)
    with pytest.raises(SettingsError):
        Settings.from_env(DEV | {"AGENT_MCP_RUNTIME_ARNS": "arn:aws:s3:::bucket"})
    assert runtime_url(ARN) == (
        "https://bedrock-agentcore.eu-west-1.amazonaws.com/runtimes/"
        "arn%3Aaws%3Abedrock-agentcore%3Aeu-west-1%3A123456789012%3Aruntime%2Ftools_mcp-abc123/invocations?qualifier=DEFAULT"
    )
    with pytest.raises(SettingsError):
        runtime_url("nope")


def test_sigv4_signs_requests_for_the_agentcore_service():
    session = boto3.Session(aws_access_key_id="AKIDEXAMPLE", aws_secret_access_key="secret", region_name="eu-west-1")
    request = httpx.Request("POST", runtime_url(ARN), json={"jsonrpc": "2.0"})
    signed = next(SigV4("eu-west-1", session).auth_flow(request))
    authorization = signed.headers["authorization"]
    assert authorization.startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
    assert "/eu-west-1/bedrock-agentcore/aws4_request" in authorization
    assert "x-amz-date" in signed.headers


def test_sigv4_without_credentials_fails_clearly():
    class NoCredentials(boto3.Session):
        def get_credentials(self):
            return None

    with pytest.raises(SettingsError):
        next(SigV4("eu-west-1", NoCredentials()).auth_flow(httpx.Request("POST", "https://example.com")))


def test_mcp_runtimes_on_agentcore_become_signed_tools():
    settings = Settings.from_env(DEV | {"AGENT_MCP_RUNTIME_ARNS": ARN})
    assert len(build_tools(settings)) == 2


def test_the_a2a_app_needs_the_token_but_keeps_ping_and_the_card_open():
    client = TestClient(create_a2a_app(Settings.from_env(TOKEN_ENV | {"AGENT_PROTOCOL": "a2a"})))
    assert client.get("/ping").status_code == 200
    assert client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "message/send"}).status_code == 401
    assert client.get("/.well-known/agent-card.json").status_code == 200
