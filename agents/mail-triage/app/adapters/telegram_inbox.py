"""Telegram intake by long polling: only the owner's private messages and button presses become commands.

Everything else is dropped without a reply and without effect (spec AC-11, AC-15). The bot token is part of the Bot API
URL, so nothing here logs a URL or an exception message (AC-24); failures are logged by type only.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic import SecretStr

logger = logging.getLogger(__name__)

API_ROOT = "https://api.telegram.org"
HTTP_OK = 200
POLL_TIMEOUT_SECONDS = 30
ALLOWED_UPDATES = ("message", "callback_query")
MAX_TEXT_CHARS = 4096  # Telegram's own message limit
MAX_BUTTON_DATA_CHARS = 64  # callback data is at most 64 bytes in the Bot API; ours is ASCII
BACKOFF_START_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class Command:
    """One thing the owner did: sent text or pressed a button."""

    kind: Literal["text", "button"]
    data: str
    chat_id: int
    message_id: int
    callback_id: str | None
    update_id: int


_BOT_PATH = re.compile(r"/bot[^/\s\"]+/")


class _MaskBotToken(logging.Filter):
    """Mask ``/bot<token>/`` in records of the HTTP client, which logs full request URLs (spec AC-24)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _BOT_PATH.sub("/bot***/", record.getMessage())
        record.args = ()
        return True


_MASK = _MaskBotToken()


def mask_bot_token_in_http_logs() -> None:
    """Mask ``/bot<token>/`` in the HTTP client's own request log (installed once per logger)."""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).addFilter(_MASK)


def _obj(value: object) -> dict[str, Any] | None:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


class LastHandledPort(Protocol):
    """The stored id of the last handled update (``PgUpdateCursor``); the router writes it, the inbox only reads it."""

    async def last(self) -> int | None:
        """The id, or ``None`` when no update was handled yet."""
        ...


class TelegramInbox:
    """Reads updates with ``getUpdates`` and keeps the offset so no update is lost or repeated.

    After a restart polling resumes just after the stored id of the last handled update, and a redelivered update at or
    below it is dropped (RT-5). ``rewind`` asks for an update again when its handling failed.
    """

    def __init__(  # noqa: PLR0913, PLR0917 - every dependency is injected for tests
        self,
        client: httpx.AsyncClient,
        token: SecretStr,
        allowed_user_id: int,
        allowed_chat_id: int,
        cursor: LastHandledPort,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        poll_timeout: int = POLL_TIMEOUT_SECONDS,
    ) -> None:
        """Wire the shared HTTP client, the bot token and the single allowed user and chat."""
        self._client = client
        mask_bot_token_in_http_logs()
        self._token = token
        self._user = allowed_user_id
        self._chat = allowed_chat_id
        self._cursor = cursor
        self._sleep = sleep
        self._timeout = poll_timeout
        self._offset: int | None = None
        self._backoff = BACKOFF_START_SECONDS

    def rewind(self, update_id: int) -> None:
        """Ask for ``update_id`` (and what follows) again on the next poll: its handling failed."""
        self._offset = update_id

    async def poll_once(self) -> list[Command]:
        """Fetch one batch; return the owner's commands. On failure wait with backoff and return nothing."""
        handled = await self._cursor.last()
        if self._offset is None and handled is not None:
            self._offset = handled + 1  # the first poll after a start resumes after the last handled update
        updates = await self._fetch()
        if updates is None:
            await self._sleep(self._backoff)
            self._backoff = min(BACKOFF_MAX_SECONDS, self._backoff * 2)
            return []
        self._backoff = BACKOFF_START_SECONDS
        commands: list[Command] = []
        for update in updates:
            update_id = update.get("update_id")
            if not isinstance(update_id, int):
                continue  # a real update always has an id; without one it cannot be tracked or deduplicated
            if handled is not None and update_id <= handled:
                continue  # handled before the last stop: Telegram redelivered it
            self._offset = max(self._offset or 0, update_id + 1)
            command = self._accept(update, update_id)
            if command is not None:
                commands.append(command)
        return commands

    async def _fetch(self) -> list[dict[str, Any]] | None:
        url = f"{API_ROOT}/bot{self._token.get_secret_value()}/getUpdates"
        payload: dict[str, Any] = {"timeout": self._timeout, "allowed_updates": list(ALLOWED_UPDATES)}
        if self._offset is not None:
            payload["offset"] = self._offset
        try:
            response = await self._client.post(url, json=payload, timeout=self._timeout + 10)
        except httpx.TransportError as error:  # never log the error text: it may contain the URL
            logger.warning("telegram polling failed kind=%s", type(error).__name__)
            return None
        if response.status_code != HTTP_OK:
            logger.warning("telegram polling refused status=%d", response.status_code)
            return None
        try:
            result = response.json()["result"]
        except (ValueError, KeyError, TypeError):
            logger.warning("telegram polling returned an unreadable body")
            return None
        if not isinstance(result, list):
            return None
        items = (_obj(item) for item in cast("list[object]", result))
        return [item for item in items if item is not None]

    def _accept(self, update: dict[str, Any], update_id: int) -> Command | None:
        message, query = _obj(update.get("message")), _obj(update.get("callback_query"))
        if message is not None:
            return self._text_command(message, update_id)
        if query is not None:
            return self._button_command(query, update_id)
        return None  # edited messages, channel posts, inline queries and everything else

    def _text_command(self, message: dict[str, Any], update_id: int) -> Command | None:
        text = message.get("text")
        message_id = message.get("message_id")
        if not (isinstance(text, str) and isinstance(message_id, int)):
            return None
        if not self._is_owner(message.get("from"), message.get("chat")):
            return None
        return Command("text", text[:MAX_TEXT_CHARS], self._chat, message_id, None, update_id)

    def _button_command(self, query: dict[str, Any], update_id: int) -> Command | None:
        data, callback_id, origin = query.get("data"), query.get("id"), _obj(query.get("message"))
        if not (isinstance(data, str) and isinstance(callback_id, str) and origin is not None):
            return None
        message_id = origin.get("message_id")
        if not isinstance(message_id, int) or not self._is_owner(query.get("from"), origin.get("chat")):
            return None
        return Command("button", data[:MAX_BUTTON_DATA_CHARS], self._chat, message_id, callback_id, update_id)

    def _is_owner(self, sender_value: object, chat_value: object) -> bool:
        sender, chat = _obj(sender_value), _obj(chat_value)
        if sender is None or chat is None:
            return False
        return sender.get("id") == self._user and chat.get("id") == self._chat and chat.get("type") == "private"
