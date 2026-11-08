"""Telegram sending to the owner's chat (guardrail-telegram; spec AC-21, AC-24)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.adapters.telegram_outbox import TelegramError, TelegramOutbox
from app.core.alert_text import AlertMessage, Button

TOKEN = "123456:ABC-secret-token"  # noqa: S105 - a fake token for tests
CHAT = 4242


class FakeTelegram:
    def __init__(self, *answers: httpx.Response | Exception) -> None:
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


def ok(message_id: int = 77) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": {"message_id": message_id}})


def outbox(fake: FakeTelegram, sleeps: list[float] | None = None) -> TelegramOutbox:
    async def sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return TelegramOutbox(
        client=httpx.AsyncClient(transport=httpx.MockTransport(fake)),
        token=SecretStr(TOKEN),
        chat_id=CHAT,
        sleep=sleep,
    )


async def test_given_an_alert_with_buttons_when_sent_then_it_goes_to_the_owner_chat_as_html_with_a_keyboard() -> None:
    fake = FakeTelegram(ok(901))
    message = AlertMessage("<b>Hi</b>", (Button("Reply", "reply:1"), Button("Later", "later:1")))

    sent_id = await outbox(fake).send(message)

    assert sent_id == 901
    request = fake.requests[0]
    assert request.url.scheme == "https"
    assert request.url.path == f"/bot{TOKEN}/sendMessage"
    body = fake.body()
    assert body["chat_id"] == CHAT
    assert body["text"] == "<b>Hi</b>"
    assert body["parse_mode"] == "HTML"
    assert body["reply_markup"] == {
        "inline_keyboard": [
            [{"text": "Reply", "callback_data": "reply:1"}],
            [{"text": "Later", "callback_data": "later:1"}],
        ]
    }
    assert body["link_preview_options"] == {"is_disabled": True}


async def test_given_a_message_without_buttons_when_sent_then_there_is_no_keyboard() -> None:
    fake = FakeTelegram(ok())

    await outbox(fake).send(AlertMessage("digest", ()))

    assert "reply_markup" not in fake.body()


async def test_given_a_short_note_when_said_then_it_is_plain_text_without_a_parse_mode() -> None:
    fake = FakeTelegram(ok())

    await outbox(fake).say("Cancelled <b>not bold</b>")

    body = fake.body()
    assert body["text"] == "Cancelled <b>not bold</b>"
    assert "parse_mode" not in body
    assert body["chat_id"] == CHAT


async def test_given_a_text_over_the_limit_when_sent_then_it_is_cut_not_failed() -> None:
    fake = FakeTelegram(ok())

    await outbox(fake).say("x" * 5000)

    assert len(fake.body()["text"]) == 4096


async def test_given_a_rate_limit_when_sent_then_it_waits_for_retry_after_and_succeeds() -> None:
    sleeps: list[float] = []
    limited = httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 3}})
    fake = FakeTelegram(limited, ok(5))

    await outbox(fake, sleeps).say("hi")

    assert len(fake.requests) == 2
    assert sleeps == [3]


@pytest.mark.parametrize(
    "failure", [httpx.ConnectError("down"), httpx.Response(502), httpx.Response(401, json={"ok": False})]
)
async def test_given_telegram_keeps_failing_when_sent_then_an_error_without_token_or_url_is_raised(
    failure: httpx.Response | Exception,
) -> None:
    fake = FakeTelegram(failure)

    with pytest.raises(TelegramError) as caught:
        await outbox(fake).say("hi")

    assert TOKEN not in str(caught.value)
    assert "api.telegram.org" not in str(caught.value)


async def test_given_a_failure_when_logged_then_the_token_never_appears(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    leaky = httpx.ConnectError(f"cannot reach https://api.telegram.org/bot{TOKEN}/sendMessage")

    with pytest.raises(TelegramError):
        await outbox(FakeTelegram(leaky)).say("hi")

    assert TOKEN not in caplog.text


async def test_given_a_button_press_when_acknowledged_then_the_callback_query_is_answered() -> None:
    fake = FakeTelegram(httpx.Response(200, json={"ok": True, "result": True}))

    await outbox(fake).answer_callback("cb1")

    assert fake.requests[0].url.path.endswith("/answerCallbackQuery")
    assert fake.body() == {"callback_query_id": "cb1"}


async def test_given_an_ok_false_answer_when_sent_then_it_is_an_error() -> None:
    fake = FakeTelegram(httpx.Response(200, json={"ok": False}))

    with pytest.raises(TelegramError):
        await outbox(fake).say("hi")
