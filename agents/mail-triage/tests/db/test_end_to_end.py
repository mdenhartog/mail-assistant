"""The whole agent against a real PostgreSQL with fake Gmail, Telegram and Anthropic (no real accounts needed)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.adapters.gmail_read import FetchedMail
from app.adapters.gmail_send import ConfirmedDraft
from app.settings import load_settings
from app.wiring import MailPorts, build_runner
from tests.test_settings import VALID

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.runner import Runner

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)  # 13:00 in Amsterdam: not quiet hours


class FakeGmail:
    """One urgent mail waiting in the inbox; remembers what was filed and sent."""

    def __init__(self) -> None:
        self.mail = FetchedMail(
            message_id="gm-1",
            thread_id="t-1",
            sender="boss@example.com",
            reply_to=None,
            subject="Invoice due Friday",
            text="Please pay the attached invoice by Friday.",
            has_attachment=False,
            headers={"Authentication-Results": "mx; spf=pass; dkim=pass; dmarc=pass"},
        )
        self.filed: list[tuple[str, str]] = []
        self.sent: list[tuple[FetchedMail, ConfirmedDraft]] = []

    def list_new(self, history_id: str | None) -> tuple[list[str], str]:
        return ([], "100") if history_id is None else (["gm-1"], "200")

    def fetch(self, message_id: str) -> FetchedMail:
        assert message_id == "gm-1"
        return self.mail

    def ensure_label(self, name: str) -> str:
        return f"id:{name}"

    def file(self, message_id: str, label_id: str) -> None:
        self.filed.append((message_id, label_id))

    def check_repliable(self, original: FetchedMail) -> None:
        del original

    def send_reply(self, original: FetchedMail, draft: ConfirmedDraft) -> str:
        self.sent.append((original, draft))
        return "sent-1"


class FakeInternet:
    """Anthropic and Telegram in one transport. Telegram updates are handed out from a queue."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.updates: list[list[dict[str, Any]]] = []
        self.model_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.anthropic.com":
            self.model_calls += 1
            verdict = {
                "category": "Finance",
                "urgent": True,
                "reason": "Invoice due on Friday",
                "summary": "The supplier wants payment.",
                "confidence": 0.95,
            }
            return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(verdict)}]})
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "getUpdates":
            batch = self.updates.pop(0) if self.updates else []
            return httpx.Response(200, json={"ok": True, "result": batch})
        if method == "sendMessage":
            self.messages.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1000 + len(self.messages)}})
        return httpx.Response(200, json={"ok": True, "result": True})


def tap(update_id: int, data: str, message_id: int = 9) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb{update_id}",
            "from": {"id": 4242},
            "data": data,
            "message": {"message_id": message_id, "chat": {"id": 4242, "type": "private"}},
        },
    }


def typed(update_id: int, words: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": 4242},
            "chat": {"id": 4242, "type": "private"},
            "text": words,
        },
    }


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


async def test_given_an_urgent_mail_when_the_agent_runs_then_it_is_filed_alerted_and_replied_to_after_confirmation(
    engine: AsyncEngine,
) -> None:
    gmail, internet = FakeGmail(), FakeInternet()
    settings = load_settings({**VALID, "TOKEN_ENCRYPTION_KEY": "unused-in-this-test"})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    run: Runner = build_runner(
        settings,
        sessions=sessions,
        client=httpx.AsyncClient(transport=httpx.MockTransport(internet)),
        mailbox=gmail,
        sender=gmail,
        own_address="marco@example.com",
        heartbeat=_heartbeat(),
        now=lambda: NOW,
    )
    store = async_sessionmaker(engine)
    async with store.begin() as session:
        await session.execute(text("insert into poll_state (id, history_id) values (1, '100')"))

    await run.mail_cycle()

    assert gmail.filed == [("gm-1", "id:Assistant/Finance")]
    [alert] = internet.messages
    assert "boss@example.com" in alert["text"]
    assert "Invoice due Friday" in alert["text"]
    buttons = [b["callback_data"] for row in alert["reply_markup"]["inline_keyboard"] for b in row]
    assert buttons[0].startswith("reply:")
    alert_id = buttons[0].split(":")[1]

    internet.updates = [[tap(1, f"reply:{alert_id}")], [typed(2, "Thanks, I will pay on Friday.")]]
    await run.telegram_cycle()
    await run.telegram_cycle()

    draft_message = internet.messages[-1]
    assert "Thanks, I will pay on Friday." in draft_message["text"]
    send_data = next(
        b["callback_data"]
        for row in draft_message["reply_markup"]["inline_keyboard"]
        for b in row
        if b["text"] == "Send"
    )
    assert gmail.sent == []  # nothing is sent before the confirmation

    internet.updates = [[tap(3, send_data)]]
    await run.telegram_cycle()

    [(original, draft)] = gmail.sent
    assert original.message_id == "gm-1"
    assert draft.body == "Thanks, I will pay on Friday."
    assert draft.sender == "marco@example.com"
    async with engine.connect() as connection:
        state = (await connection.execute(text("select state from alert"))).scalar_one()
        audit = [row[0] for row in (await connection.execute(text("select kind from audit_log order by id"))).all()]
    assert state == "closed"
    assert audit == ["alert_sent", "reply_drafted", "reply_sent"]
    assert internet.model_calls == 1


async def test_given_the_agent_runs_twice_when_the_same_mail_is_listed_then_it_alerts_once(engine: AsyncEngine) -> None:
    gmail, internet = FakeGmail(), FakeInternet()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    run = build_runner(
        load_settings(VALID),
        sessions=sessions,
        client=httpx.AsyncClient(transport=httpx.MockTransport(internet)),
        mailbox=gmail,
        sender=gmail,
        own_address="marco@example.com",
        heartbeat=_heartbeat(),
        now=lambda: NOW,
    )
    async with sessions.begin() as session:
        await session.execute(text("insert into poll_state (id, history_id) values (1, '100')"))

    await run.mail_cycle()
    async with sessions.begin() as session:
        await session.execute(text("update poll_state set history_id = '100'"))  # Gmail lists it again
    await run.mail_cycle()

    assert len(internet.messages) == 1
    assert internet.model_calls == 1
    assert len(gmail.filed) == 1


def _heartbeat() -> Any:
    from pathlib import Path  # noqa: PLC0415
    from tempfile import mkdtemp  # noqa: PLC0415

    return Path(mkdtemp()) / "heartbeat"


_ = SecretStr  # imported for typing parity with the other tests


def test_given_the_gmail_ports_when_used_then_each_call_goes_to_the_reader_or_the_sender() -> None:
    gmail = FakeGmail()
    ports = MailPorts(gmail, gmail)  # type: ignore[arg-type]

    assert ports.list_new("1") == (["gm-1"], "200")
    assert ports.fetch("gm-1") is gmail.mail
    assert ports.ensure_label("Assistant/Finance") == "id:Assistant/Finance"
    ports.file("gm-1", "id:Assistant/Finance")
    ports.check_repliable(gmail.mail)
    assert ports.send_reply(gmail.mail, ConfirmedDraft("d1", "marco@example.com", None, "Hi")) == "sent-1"
    assert gmail.filed == [("gm-1", "id:Assistant/Finance")]
