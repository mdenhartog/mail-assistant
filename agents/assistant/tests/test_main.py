from starlette.testclient import TestClient

from app.agent import build_agent
from app.main import create_app
from app.memory import AgentPool
from app.settings import Settings
from tests import DEV

from .fakes import ScriptedModel

SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"


def client_for(settings: Settings, reply: str = "pong") -> TestClient:
    pool = AgentPool(lambda s, a: build_agent(settings, s, a, model=ScriptedModel(reply)), settings.max_sessions)
    return TestClient(create_app(settings, pool))


def test_ping_reports_healthy(settings: Settings):
    response = client_for(settings).get("/ping")
    assert response.status_code == 200
    assert response.json()["status"] == "Healthy"


def test_invocation_returns_the_answer_and_the_session(settings: Settings):
    session = "s-" + "1" * 33
    response = client_for(settings).post("/invocations", json={"prompt": "ping"}, headers={SESSION_HEADER: session})
    assert response.status_code == 200
    assert response.json()["response"] == "pong"
    assert response.json()["session_id"] == session


def test_a_session_id_is_created_when_the_caller_sends_none(settings: Settings):
    response = client_for(settings).post("/invocations", json={"prompt": "ping"})
    assert len(response.json()["session_id"]) >= 32


def test_invalid_requests_are_refused(settings: Settings):
    client = client_for(settings)
    assert client.post("/invocations", json={"prompt": ""}).status_code == 422
    assert client.post("/invocations", json={"prompt": "x", "extra": 1}).status_code == 422
    assert client.post("/invocations", json={}).status_code == 422


def test_too_long_prompts_are_refused(settings: Settings):
    small = Settings.from_env(DEV | {"AGENT_MAX_PROMPT_CHARS": "5"})
    assert client_for(small).post("/invocations", json={"prompt": "123456"}).status_code == 413
