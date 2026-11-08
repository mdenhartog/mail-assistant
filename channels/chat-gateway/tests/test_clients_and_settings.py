import io
import json

import httpx2
import pytest

from app.agent_client import AgentCoreClient, AgentError, HttpAgentClient, runtime_session_id
from app.dedupe import SeenCache
from app.main import create_app_from_env
from app.settings import Settings, SettingsError
from app.telegram import HttpTelegramSender
from app.whatsapp import HttpWhatsAppSender

BASE = {
    "AGENT_URL": "http://agent:8080/",
    "TELEGRAM_BOT_TOKEN": "1:a",
    "TELEGRAM_WEBHOOK_SECRET": "s" * 20,
    "TELEGRAM_ALLOWED_CHAT_IDS": "1",
}


def test_session_ids_are_stable_per_chat_and_long_enough():
    assert runtime_session_id("telegram", "1") == runtime_session_id("telegram", "1")
    assert runtime_session_id("telegram", "1") != runtime_session_id("telegram", "2")
    assert len(runtime_session_id("x", "1")) >= 33


async def test_http_client_posts_the_contract_and_reads_the_answer():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"], seen["auth"] = json.loads(request.content), request.headers.get("authorization")
        seen["session"] = request.headers.get("x-amzn-bedrock-agentcore-runtime-session-id")
        return httpx2.Response(200, json={"response": "hi"})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        client = HttpAgentClient(http, "http://agent:8080", "tok", 5)
        assert await client.ask("p", "s" * 40, "u") == "hi"
    assert seen["body"] == {"prompt": "p", "session_id": "s" * 40, "actor_id": "u"}
    assert (seen["auth"], seen["session"]) == ("Bearer tok", "s" * 40)


async def test_http_client_errors_never_contain_the_prompt():
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(lambda _r: httpx2.Response(500))) as http:
        with pytest.raises(AgentError) as error:
            await HttpAgentClient(http, "http://agent", None, 5).ask("secret prompt", "s" * 40, "u")
    assert "secret prompt" not in str(error.value)


async def test_agentcore_client_invokes_the_runtime_with_the_session():
    calls = []

    class Boto:
        def invoke_agent_runtime(self, **kwargs):
            calls.append(kwargs)
            return {"response": io.BytesIO(b'{"response": "from runtime"}')}

    answer = await AgentCoreClient(Boto(), "arn:aws:bedrock-agentcore:eu-west-1:1:runtime/x").ask("p", "s" * 40, "u")
    assert answer == "from runtime"
    assert calls[0]["agentRuntimeArn"].endswith("runtime/x") and calls[0]["runtimeSessionId"] == "s" * 40


async def test_agentcore_failures_become_agent_errors():
    class Broken:
        def invoke_agent_runtime(self, **_kwargs):
            raise RuntimeError("boom with secret prompt")

    with pytest.raises(AgentError) as error:
        await AgentCoreClient(Broken(), "arn").ask("secret prompt", "s" * 40, "u")
    assert "secret prompt" not in str(error.value)


async def test_senders_post_to_the_official_endpoints():
    urls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        urls.append((str(request.url), request.headers.get("authorization")))
        return httpx2.Response(200, json={})

    settings = Settings.from_env(
        {
            **BASE,
            "WHATSAPP_APP_SECRET": "a",
            "WHATSAPP_VERIFY_TOKEN": "v" * 20,
            "WHATSAPP_ACCESS_TOKEN": "t",
            "WHATSAPP_PHONE_NUMBER_ID": "55",
            "WHATSAPP_ALLOWED_NUMBERS": "1",
        }
    )
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        await HttpTelegramSender(http, "1:a").send(1, "x")
        assert settings.whatsapp is not None
        await HttpWhatsAppSender(http, settings.whatsapp).send("1", "x")
    assert urls[0][0] == "https://api.telegram.org/bot1:a/sendMessage"
    assert urls[1] == (f"https://graph.facebook.com/{settings.whatsapp.api_version}/55/messages", "Bearer t")


async def test_sender_errors_do_not_leak_the_token_url():
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(lambda _r: httpx2.Response(401))) as http:
        with pytest.raises(AgentError) as error:
            await HttpTelegramSender(http, "123:SECRET").send(1, "x")
    assert "SECRET" not in str(error.value)


def test_seen_cache_expires_and_is_bounded():
    now = [0.0]
    cache = SeenCache(max_items=2, ttl_seconds=10, clock=lambda: now[0])
    assert cache.first_time("a") and not cache.first_time("a")
    cache.first_time("b")
    cache.first_time("c")
    assert cache.first_time("a")  # evicted by the bound
    now[0] = 100
    assert cache.first_time("c")  # expired by the time-to-live


@pytest.mark.parametrize(
    "env",
    [
        {"AGENT_URL": "http://a"},  # no channel
        {**BASE, "TELEGRAM_WEBHOOK_SECRET": "short"},
        {**BASE, "TELEGRAM_ALLOWED_CHAT_IDS": ""},
        {**BASE, "TELEGRAM_ALLOWED_CHAT_IDS": "abc"},
        {"AGENT_URL": "http://a", "WHATSAPP_ACCESS_TOKEN": "t"},  # partly configured
        {**BASE, "AGENT_BACKEND": "carrier-pigeon"},
        {**BASE, "AGENT_BACKEND": "agentcore"},
        {k: v for k, v in BASE.items() if k != "AGENT_URL"},
    ],
)
def test_unsafe_or_incomplete_configuration_is_refused(env):
    with pytest.raises(SettingsError):
        Settings.from_env(env)


def test_valid_settings_normalise_values():
    settings = Settings.from_env(BASE)
    assert settings.agent_url == "http://agent:8080"
    assert settings.telegram is not None and settings.telegram.allowed_chat_ids == frozenset({1})


def test_production_wiring_builds_from_the_environment(monkeypatch):
    for key, value in BASE.items():
        monkeypatch.setenv(key, value)
    assert create_app_from_env().title == "chat-gateway"


@pytest.mark.parametrize("error", [httpx2.ConnectError("refused"), httpx2.ReadTimeout("slow")])
async def test_transport_failures_become_agent_errors_without_the_url(error):
    def fail(_request: httpx2.Request) -> httpx2.Response:
        raise error

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(fail)) as http:
        with pytest.raises(AgentError) as agent_error:
            await HttpAgentClient(http, "http://agent:8080", None, 5).ask("p", "s" * 40, "u")
        with pytest.raises(AgentError) as telegram_error:
            await HttpTelegramSender(http, "123:SECRET").send(1, "x")
    assert "agent:8080" not in str(agent_error.value)
    assert "SECRET" not in str(telegram_error.value)
    assert telegram_error.value.__cause__ is None


async def test_an_agent_answer_that_is_not_json_is_an_agent_error():
    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda _r: httpx2.Response(200, content=b"<html>"))
    ) as http:
        with pytest.raises(AgentError):
            await HttpAgentClient(http, "http://agent", None, 5).ask("p", "s" * 40, "u")
