import httpx2
import pytest
from starlette.testclient import TestClient

from app.agent_client import HttpAgentClient
from app.main import create_app
from app.settings import Settings

from .fakes import FakeAgent, FakeSender

SECRET = "s" * 24
ENV = {
    "AGENT_URL": "http://agent:8080",
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "TELEGRAM_WEBHOOK_SECRET": SECRET,
    "TELEGRAM_ALLOWED_CHAT_IDS": "111,222",
}
HEADER = {"X-Telegram-Bot-Api-Secret-Token": SECRET}


def update(chat_id: int = 111, text: str | None = "hi", update_id: int = 1) -> dict:
    message = {"message_id": 5, "chat": {"id": chat_id, "type": "private"}, "from": {"id": 9, "first_name": "A"}}
    if text is not None:
        message["text"] = text
    return {"update_id": update_id, "message": message, "unknown_future_field": True}


@pytest.fixture
def parts():
    agent, sender = FakeAgent(), FakeSender()
    client = TestClient(create_app(Settings.from_env(ENV), agent, telegram_sender=sender))
    return client, agent, sender


def test_a_valid_message_is_answered_in_the_same_chat(parts):
    client, agent, sender = parts
    assert client.post("/telegram/webhook", json=update(), headers=HEADER).status_code == 200
    assert sender.sent == [(111, "hello back")]
    prompt, session, actor = agent.calls[0]
    assert (prompt, actor) == ("hi", "telegram:9")
    assert len(session) >= 33


@pytest.mark.parametrize("headers", [{}, {"X-Telegram-Bot-Api-Secret-Token": "wrong"}])
def test_requests_without_the_secret_are_rejected_and_never_reach_the_agent(parts, headers):
    client, agent, sender = parts
    assert client.post("/telegram/webhook", json=update(), headers=headers).status_code == 401
    assert agent.calls == [] and sender.sent == []


def test_chats_outside_the_allow_list_are_ignored(parts):
    client, agent, sender = parts
    assert client.post("/telegram/webhook", json=update(chat_id=999), headers=HEADER).status_code == 200
    assert agent.calls == [] and sender.sent == []


def test_a_redelivered_update_is_answered_once(parts):
    client, _agent, sender = parts
    for _ in range(3):
        client.post("/telegram/webhook", json=update(update_id=7), headers=HEADER)
    assert len(sender.sent) == 1


def test_non_text_updates_and_garbage_are_handled(parts):
    client, agent, _sender = parts
    assert client.post("/telegram/webhook", json=update(text=None), headers=HEADER).status_code == 200
    assert client.post("/telegram/webhook", json={"update_id": 3}, headers=HEADER).status_code == 200
    assert client.post("/telegram/webhook", content=b"not json", headers=HEADER).status_code == 400
    assert agent.calls == []


def test_an_agent_failure_gives_a_generic_apology_without_details():
    agent, sender = FakeAgent(fail=True), FakeSender()
    client = TestClient(create_app(Settings.from_env(ENV), agent, telegram_sender=sender))
    client.post("/telegram/webhook", json=update(), headers=HEADER)
    assert sender.sent == [(111, "Sorry, something went wrong. Please try again later.")]


def test_ping_is_open(parts):
    assert parts[0].get("/ping").json() == {"status": "Healthy"}


def test_a_slow_or_unreachable_agent_still_gets_the_apology():
    def timeout(_request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow")

    agent = HttpAgentClient(httpx2.AsyncClient(transport=httpx2.MockTransport(timeout)), "http://agent:8080", None, 1)
    sender = FakeSender()
    client = TestClient(create_app(Settings.from_env(ENV), agent, telegram_sender=sender))
    client.post("/telegram/webhook", json=update(), headers=HEADER)
    assert sender.sent == [(111, "Sorry, something went wrong. Please try again later.")]
