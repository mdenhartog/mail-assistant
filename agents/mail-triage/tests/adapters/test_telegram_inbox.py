"""U-11: Telegram intake by long polling (spec AC-11, AC-15, AC-24; guardrail-telegram)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.adapters.telegram_inbox import Command, TelegramInbox

TOKEN = "123456:ABC-secret-token"  # noqa: S105 - a fake token for tests
USER = 4242
CHAT = 4242


def message(
    update_id: int, text: str = "hello", user: int = USER, chat: int = CHAT, kind: str = "private"
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {"message_id": 7, "from": {"id": user}, "chat": {"id": chat, "type": kind}, "text": text},
    }


def button(update_id: int, data: str = "reply:12", user: int = USER, chat: int = CHAT) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "cb1",
            "from": {"id": user},
            "data": data,
            "message": {"message_id": 9, "chat": {"id": chat, "type": "private"}},
        },
    }


class FakeTelegram:
    """Answers getUpdates from a script and records every request."""

    def __init__(self, *batches: list[dict[str, Any]] | Exception | int) -> None:
        self.batches = list(batches)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.batches.pop(0) if self.batches else []
        if isinstance(step, Exception):
            raise step
        if isinstance(step, int):
            return httpx.Response(step, json={"ok": False})
        return httpx.Response(200, json={"ok": True, "result": step})

    def offsets(self) -> list[int | None]:
        return [json.loads(request.content).get("offset") for request in self.requests]


def make_inbox(fake: FakeTelegram, sleeps: list[float] | None = None) -> TelegramInbox:
    async def sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return TelegramInbox(
        client=httpx.AsyncClient(transport=httpx.MockTransport(fake)),
        token=SecretStr(TOKEN),
        allowed_user_id=USER,
        allowed_chat_id=CHAT,
        sleep=sleep,
    )


async def test_given_an_update_from_the_owner_when_polled_then_a_command_is_produced() -> None:
    inbox = make_inbox(FakeTelegram([message(1, "3"), button(2, "reply:12")]))

    commands = await inbox.poll_once()

    assert commands == [
        Command(kind="text", data="3", chat_id=CHAT, message_id=7, callback_id=None),
        Command(kind="button", data="reply:12", chat_id=CHAT, message_id=9, callback_id="cb1"),
    ]


@pytest.mark.parametrize(
    "update",
    [
        message(1, user=999),  # another user
        message(2, chat=999),  # another chat
        message(3, kind="group"),  # a group, even with the right ids
        button(4, user=999),
        button(5, chat=999),
        {"update_id": 6, "edited_message": message(6)["message"]},
        {"update_id": 7, "channel_post": message(7)["message"]},
        {"update_id": 8, "inline_query": {"id": "q", "from": {"id": USER}, "query": "x"}},
        {"update_id": 9, "message": {"message_id": 1, "from": {"id": USER}, "chat": {"id": CHAT, "type": "private"}}},
        {"update_id": 10, "message": "garbage"},
        {"update_id": 11},
    ],
)
async def test_given_an_update_from_anyone_else_or_of_an_unknown_shape_when_polled_then_it_is_dropped(
    update: dict[str, Any],
) -> None:
    fake = FakeTelegram([update])
    inbox = make_inbox(fake)

    assert await inbox.poll_once() == []
    assert len(fake.requests) == 1  # no reply, no other call: dropping has no effect


async def test_given_dropped_updates_when_polled_again_then_the_offset_moves_past_them() -> None:
    fake = FakeTelegram([message(5, user=999), message(6)], [])
    inbox = make_inbox(fake)

    await inbox.poll_once()
    await inbox.poll_once()

    assert fake.offsets() == [None, 7]


async def test_given_a_long_text_and_long_button_data_when_polled_then_they_are_cut() -> None:
    inbox = make_inbox(FakeTelegram([message(1, "x" * 5000), button(2, "y" * 200)]))

    text, data = await inbox.poll_once()

    assert len(text.data) == 4096
    assert len(data.data) == 64


async def test_given_a_polling_failure_when_polled_then_it_backs_off_and_keeps_the_offset() -> None:
    sleeps: list[float] = []
    fake = FakeTelegram([message(5)], httpx.ConnectError("down"), 502, [message(6)])
    inbox = make_inbox(fake, sleeps)

    first = await inbox.poll_once()
    failed_a = await inbox.poll_once()
    failed_b = await inbox.poll_once()
    after = await inbox.poll_once()

    assert [len(first), failed_a, failed_b, len(after)] == [1, [], [], 1]
    assert len(sleeps) == 2
    assert sleeps[1] > sleeps[0]  # backoff grows while it keeps failing
    assert fake.offsets() == [None, 6, 6, 6]  # the failed calls and the retry all ask from the same offset
    assert sleeps[0] > 0


async def test_given_a_failure_then_success_when_polled_then_backoff_resets() -> None:
    sleeps: list[float] = []
    fake = FakeTelegram(httpx.ReadTimeout("slow"), [], httpx.ReadTimeout("slow"))
    inbox = make_inbox(fake, sleeps)

    await inbox.poll_once()
    await inbox.poll_once()
    await inbox.poll_once()

    assert sleeps[0] == sleeps[1]


async def test_given_a_failure_when_logged_then_neither_the_token_nor_the_url_appears(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    leaky = httpx.ConnectError(f"cannot reach https://api.telegram.org/bot{TOKEN}/getUpdates")
    inbox = make_inbox(FakeTelegram(leaky, 401))

    await inbox.poll_once()
    await inbox.poll_once()

    assert TOKEN not in caplog.text
    assert "/bot***/" in caplog.text  # the HTTP client's own request log is masked, not silenced


async def test_given_the_request_when_made_then_it_uses_https_and_asks_only_for_messages_and_buttons() -> None:
    fake = FakeTelegram([])
    await make_inbox(fake).poll_once()

    request = fake.requests[0]
    assert request.url.scheme == "https"
    assert request.url.path == f"/bot{TOKEN}/getUpdates"
    body = json.loads(request.content)
    assert sorted(body["allowed_updates"]) == ["callback_query", "message"]
    assert body["timeout"] > 0


@pytest.mark.parametrize("body", [b"<html>", b'{"ok": true, "result": "x"}', b'{"ok": false}'])
async def test_given_an_unreadable_response_when_polled_then_it_is_treated_as_a_failure(body: bytes) -> None:
    sleeps: list[float] = []
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=body))
    inbox = TelegramInbox(
        client=httpx.AsyncClient(transport=transport),
        token=SecretStr(TOKEN),
        allowed_user_id=USER,
        allowed_chat_id=CHAT,
        sleep=lambda seconds: _record(sleeps, seconds),
    )

    assert await inbox.poll_once() == []
    assert len(sleeps) == 1


async def _record(sleeps: list[float], seconds: float) -> None:
    sleeps.append(seconds)


async def test_given_items_that_are_not_objects_when_polled_then_they_are_ignored() -> None:
    fake = FakeTelegram(["junk", 5, message(1)])  # type: ignore[list-item]
    fake.batches = [["junk", 5, message(1)]]  # type: ignore[list-item]

    assert len(await make_inbox(fake).poll_once()) == 1
