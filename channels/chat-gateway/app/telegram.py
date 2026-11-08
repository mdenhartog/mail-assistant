"""Telegram Bot API webhook. Telegram does not sign payloads: it repeats the secret you registered in a header."""

from __future__ import annotations

import hmac
import logging
from typing import TYPE_CHECKING, Protocol

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent_client import AgentError, post_json, runtime_session_id

if TYPE_CHECKING:
    import httpx2

    from app.agent_client import AgentClient
    from app.dedupe import SeenCache
    from app.settings import TelegramSettings

log = logging.getLogger("channel.telegram")
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"  # noqa: S105  # nosec B105
MAX_TEXT = 4096
FALLBACK = "Sorry, something went wrong. Please try again later."
HTTP_OK = 200


class Chat(BaseModel):
    """The chat a message belongs to."""

    model_config = ConfigDict(extra="ignore")

    id: int


class User(BaseModel):
    """The sender."""

    model_config = ConfigDict(extra="ignore")

    id: int


class Message(BaseModel):
    """A message; only text messages reach the agent."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    chat: Chat
    sender: User | None = Field(default=None, alias="from")
    text: str | None = None


# nosemgrep: semgrep.kit-mutation-schema-without-forbid -- an inbound Telegram schema, not a mutation of ours
class Update(BaseModel):
    """A Telegram update. Telegram adds fields over time, so unknown ones are ignored (not ours to forbid)."""

    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: Message | None = None


class TelegramSender(Protocol):
    """Sends a text to a chat."""

    async def send(self, chat_id: int, text: str) -> None:
        """Send ``text`` (at most 4096 characters) to ``chat_id``."""
        ...


class HttpTelegramSender:
    """``sendMessage`` through the Bot API."""

    def __init__(self, http: httpx2.AsyncClient, bot_token: str) -> None:
        """The token is part of the URL, as Telegram requires; it is never logged."""
        self._http = http
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async def send(self, chat_id: int, text: str) -> None:
        """Send one message; raise on a non-200 answer (without the URL, which holds the token)."""
        body = {"chat_id": chat_id, "text": text[:MAX_TEXT]}
        response = await post_json(self._http, self._url, "telegram", json=body, timeout=15)
        if response.status_code != HTTP_OK:
            raise AgentError(f"telegram sendMessage answered {response.status_code}")


def accepted(update: Update, settings: TelegramSettings, seen: SeenCache) -> tuple[int, int, str] | None:
    """Return (chat id, sender id, text) when the update is a new text message from an allowed chat, else None."""
    message = update.message
    if message is None or not message.text:
        return None
    if message.chat.id not in settings.allowed_chat_ids:
        log.info("ignored a message from a chat that is not on the allow-list")
        return None
    if not seen.first_time(f"tg:{update.update_id}"):
        return None
    return message.chat.id, message.sender.id if message.sender else message.chat.id, message.text


def build_router(settings: TelegramSettings, agent: AgentClient, sender: TelegramSender, seen: SeenCache) -> APIRouter:
    """The ``/telegram/webhook`` route for one bot."""
    router = APIRouter()

    async def reply(chat_id: int, user_id: int, text: str) -> None:
        try:
            answer = await agent.ask(
                text[:MAX_TEXT], runtime_session_id("telegram", str(chat_id)), f"telegram:{user_id}"
            )
        except AgentError:
            log.warning("agent failed for a telegram chat")
            answer = FALLBACK
        try:
            await sender.send(chat_id, answer or FALLBACK)
        except AgentError:
            log.warning("telegram send failed")

    @router.post("/telegram/webhook")
    async def webhook(request: Request, background: BackgroundTasks) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        supplied = request.headers.get(SECRET_HEADER, "")
        if not hmac.compare_digest(supplied.encode(), settings.webhook_secret.encode()):
            raise HTTPException(status_code=401)
        try:
            update = Update.model_validate_json(await request.body())
        except ValidationError as error:
            raise HTTPException(status_code=400) from error
        if (job := accepted(update, settings, seen)) is not None:
            background.add_task(reply, *job)
        return {"ok": True}

    return router
