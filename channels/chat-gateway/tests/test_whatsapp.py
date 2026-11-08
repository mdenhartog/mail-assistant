import hashlib
import hmac
import json

import pytest
from starlette.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from app.whatsapp import valid_signature

from .fakes import FakeAgent, FakeSender

APP_SECRET = "app-secret-value"
VERIFY = "verify-token-of-16+"
ENV = {
    "AGENT_URL": "http://agent:8080",
    "WHATSAPP_APP_SECRET": APP_SECRET,
    "WHATSAPP_VERIFY_TOKEN": VERIFY,
    "WHATSAPP_ACCESS_TOKEN": "EAAG-token",
    "WHATSAPP_PHONE_NUMBER_ID": "10555",
    "WHATSAPP_ALLOWED_NUMBERS": "+31612345678",
}


def sign(raw: bytes, secret: str = APP_SECRET) -> dict[str, str]:
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()}


def payload(number: str = "31612345678", kind: str = "text", message_id: str = "wamid.1") -> bytes:
    message = {"id": message_id, "from": number, "type": kind}
    if kind == "text":
        message["text"] = {"body": "hello"}
    body = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "1", "changes": [{"value": {"messages": [message]}}]}],
    }
    return json.dumps(body).encode()


@pytest.fixture
def parts():
    agent, sender = FakeAgent(), FakeSender()
    return TestClient(create_app(Settings.from_env(ENV), agent, whatsapp_sender=sender)), agent, sender


def post(client, raw: bytes, headers: dict[str, str]):
    return client.post("/whatsapp/webhook", content=raw, headers=headers | {"Content-Type": "application/json"})


def test_the_handshake_echoes_the_challenge_only_with_the_verify_token(parts):
    client = parts[0]
    ok = client.get(
        "/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "4242"}
    )
    assert (ok.status_code, ok.text) == (200, "4242")
    wrong = client.get(
        "/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"}
    )
    assert wrong.status_code == 403
    assert client.get("/whatsapp/webhook", params={"hub.mode": "other", "hub.verify_token": VERIFY}).status_code == 403


def test_a_signed_message_is_answered(parts):
    client, agent, sender = parts
    raw = payload()
    assert post(client, raw, sign(raw)).status_code == 200
    assert sender.sent == [("31612345678", "hello back")]
    assert agent.calls[0][0] == "hello" and agent.calls[0][2] == "whatsapp:31612345678"


@pytest.mark.parametrize("header", [{}, {"X-Hub-Signature-256": "sha256=deadbeef"}, sign(b"other body")])
def test_unsigned_or_wrongly_signed_posts_are_rejected(parts, header):
    client, agent, sender = parts
    assert post(client, payload(), header).status_code == 401
    assert agent.calls == [] and sender.sent == []


def test_the_signature_covers_the_raw_bytes_not_the_parsed_json(parts):
    client, agent, _sender = parts
    raw = payload()
    reformatted = json.dumps(json.loads(raw), indent=2).encode()
    assert post(client, reformatted, sign(raw)).status_code == 401
    assert agent.calls == []


def test_numbers_outside_the_allow_list_and_non_text_messages_are_ignored(parts):
    client, agent, _sender = parts
    for raw in (payload(number="31699999999"), payload(kind="image", message_id="wamid.2")):
        assert post(client, raw, sign(raw)).status_code == 200
    assert agent.calls == []


def test_a_redelivered_message_is_answered_once(parts):
    client, _agent, sender = parts
    raw = payload(message_id="wamid.dup")
    for _ in range(3):
        post(client, raw, sign(raw))
    assert len(sender.sent) == 1


def test_malformed_signed_payloads_are_rejected(parts):
    raw = b'{"entry": "not a list"}'
    assert post(parts[0], raw, sign(raw)).status_code == 400


def test_valid_signature_is_constant_time_safe_for_any_header():
    assert valid_signature("s", b"x", "") is False
    assert valid_signature("s", b"x", "sha256=" + hmac.new(b"s", b"x", hashlib.sha256).hexdigest()) is True
