"""Telegram sending to the owner's chat (guardrail-telegram; spec AC-21, AC-24).

Messages go only to the one configured chat. Alert text is HTML that ``alert_text`` already escaped; short notes are
plain text with no parse mode, so nothing in them is interpreted. Text is cut at Telegram's limit rather than failing.
Errors never carry the URL or the bot token, which is part of the URL.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import httpx

from app.adapters.telegram_inbox import API_ROOT, HTTP_OK, mask_bot_token_in_http_logs

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic import SecretStr

    from app.core.alert_text import AlertMessage

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 4096
MAX_ATTEMPTS = 3
HTTP_RATE_LIMITED = 429
HTTP_SERVER_ERROR = 500
BACKOFF_SECONDS = 1.0
MAX_WAIT_SECONDS = 30.0


class TelegramError(RuntimeError):
    """A Telegram call failed. The message never contains the bot token or the URL."""


class TelegramOutbox:
    """Sends messages to Marco's chat."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        token: SecretStr,
        chat_id: int,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Wire the shared HTTP client, the bot token and the single allowed chat."""
        self._client = client
        self._token = token
        self._chat = chat_id
        self._sleep = sleep
        mask_bot_token_in_http_logs()

    async def send(self, message: AlertMessage) -> int:
        """Send an alert or digest with its buttons; return the Telegram message id."""
        payload: dict[str, Any] = {
            "chat_id": self._chat,
            "text": message.text[:MAX_TEXT_CHARS],
            "parse_mode": message.parse_mode,
            "link_preview_options": {"is_disabled": True},
        }
        if message.buttons:
            keyboard = [[{"text": b.label, "callback_data": b.data}] for b in message.buttons]
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        return await self._message_id(await self._call("sendMessage", payload))

    async def say(self, text: str) -> None:
        """Send a short plain-text note."""
        payload = {"chat_id": self._chat, "text": text[:MAX_TEXT_CHARS], "link_preview_options": {"is_disabled": True}}
        await self._call("sendMessage", payload)

    async def answer_callback(self, callback_id: str) -> None:
        """Stop the spinner on a pressed button."""
        await self._call("answerCallbackQuery", {"callback_query_id": callback_id})

    @staticmethod
    async def _message_id(result: Any) -> int:  # noqa: ANN401 - the Bot API result is untyped JSON
        try:
            return int(result["message_id"])
        except (KeyError, TypeError, ValueError):
            raise TelegramError("Telegram did not return a message id") from None

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:  # noqa: ANN401
        url = f"{API_ROOT}/bot{self._token.get_secret_value()}/{method}"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            wait = BACKOFF_SECONDS * attempt
            try:
                response = await self._client.post(url, json=payload)
            except httpx.TransportError as error:  # never log the error text: it may contain the URL
                logger.warning("telegram %s failed attempt=%d kind=%s", method, attempt, type(error).__name__)
            else:
                if response.status_code == HTTP_OK:
                    return self._result(response)
                logger.warning("telegram %s refused attempt=%d status=%d", method, attempt, response.status_code)
                if response.status_code != HTTP_RATE_LIMITED and response.status_code < HTTP_SERVER_ERROR:
                    break
                wait = max(wait, self._retry_after(response))
            if attempt < MAX_ATTEMPTS:
                await self._sleep(wait)
        raise TelegramError(f"Telegram {method} failed")

    @staticmethod
    def _result(response: httpx.Response) -> Any:  # noqa: ANN401
        try:
            body = response.json()
        except ValueError:
            raise TelegramError("Telegram returned an unreadable answer") from None
        if not isinstance(body, dict) or body.get("ok") is not True:
            raise TelegramError("Telegram did not accept the call")
        return body.get("result")

    @staticmethod
    def _retry_after(response: httpx.Response) -> float:
        try:
            return min(MAX_WAIT_SECONDS, float(response.json()["parameters"]["retry_after"]))
        except (ValueError, KeyError, TypeError):
            return 0.0
