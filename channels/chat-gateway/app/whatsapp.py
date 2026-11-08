"""WhatsApp Cloud API webhook: a GET handshake (verify token) and POSTs signed with HMAC-SHA256."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import TYPE_CHECKING, Protocol

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent_client import AgentError, post_json, runtime_session_id

if TYPE_CHECKING:
    import httpx2

    from app.agent_client import AgentClient
    from app.dedupe import SeenCache
    from app.settings import WhatsAppSettings

log = logging.getLogger("channel.whatsapp")
SIGNATURE_HEADER = "X-Hub-Signature-256"
MAX_TEXT = 4096
FALLBACK = "Sorry, something went wrong. Please try again later."
HTTP_OK = 200


class Text(BaseModel):
    """The body of a text message."""

    model_config = ConfigDict(extra="ignore")

    body: str


class InboundMessage(BaseModel):
    """One inbound message. Only ``type == "text"`` reaches the agent."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    sender: str = Field(alias="from")
    type: str
    text: Text | None = None


class Value(BaseModel):
    """The ``value`` of a change."""

    model_config = ConfigDict(extra="ignore")

    messages: list[InboundMessage] = []


class Change(BaseModel):
    """One change in an entry."""

    model_config = ConfigDict(extra="ignore")

    value: Value


class Entry(BaseModel):
    """One entry of the webhook payload."""

    model_config = ConfigDict(extra="ignore")

    changes: list[Change] = []


class Payload(BaseModel):
    """The webhook payload. Meta adds fields over time, so unknown ones are ignored."""

    model_config = ConfigDict(extra="ignore")

    entry: list[Entry] = []


class WhatsAppSender(Protocol):
    """Sends a text message to a WhatsApp number."""

    async def send(self, to: str, text: str) -> None:
        """Send ``text`` (at most 4096 characters) to ``to``."""
        ...


class HttpWhatsAppSender:
    """``POST /{phone-number-id}/messages`` on the Graph API."""

    def __init__(self, http: httpx2.AsyncClient, settings: WhatsAppSettings) -> None:
        """The access token goes in a header, never in a URL or a log line."""
        self._http = http
        self._url = f"https://graph.facebook.com/{settings.api_version}/{settings.phone_number_id}/messages"
        self._headers = {"Authorization": f"Bearer {settings.access_token}"}

    async def send(self, to: str, text: str) -> None:
        """Send one text message; raise ``AgentError`` on a non-200 answer."""
        body = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text[:MAX_TEXT]}}
        response = await post_json(self._http, self._url, "whatsapp", json=body, headers=self._headers, timeout=15)
        if response.status_code != HTTP_OK:
            raise AgentError(f"whatsapp send answered {response.status_code}")


def valid_signature(app_secret: str, raw_body: bytes, header: str) -> bool:
    """Check ``sha256=<hex>`` against the HMAC of the RAW body, in constant time."""
    expected = "sha256=" + hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), header.encode())


def valid_handshake(verify_token: str, query: dict[str, str]) -> bool:
    """The GET handshake: mode subscribe and the verify token, compared in constant time."""
    supplied = query.get("hub.verify_token", "")
    return query.get("hub.mode") == "subscribe" and hmac.compare_digest(supplied.encode(), verify_token.encode())


def accepted(payload: Payload, settings: WhatsAppSettings, seen: SeenCache) -> list[tuple[str, str]]:
    """The (number, text) pairs of new text messages from allowed numbers."""
    jobs: list[tuple[str, str]] = []
    for entry in payload.entry:
        for change in entry.changes:
            for message in change.value.messages:
                if message.type != "text" or message.text is None:
                    continue
                if message.sender.lstrip("+") not in settings.allowed_numbers:
                    log.info("ignored a message from a number that is not on the allow-list")
                elif seen.first_time(f"wa:{message.id}"):
                    jobs.append((message.sender, message.text.body))
    return jobs


async def reply(agent: AgentClient, sender: WhatsAppSender, number: str, text: str) -> None:
    """Ask the agent and send the answer; failures give a generic apology and never log message content."""
    try:
        answer = await agent.ask(text[:MAX_TEXT], runtime_session_id("whatsapp", number), f"whatsapp:{number}")
    except AgentError:
        log.warning("agent failed for a whatsapp number")
        answer = FALLBACK
    try:
        await sender.send(number, answer or FALLBACK)
    except AgentError:
        log.warning("whatsapp send failed")


def build_router(settings: WhatsAppSettings, agent: AgentClient, sender: WhatsAppSender, seen: SeenCache) -> APIRouter:
    """The ``/whatsapp/webhook`` routes for one phone number."""
    router = APIRouter()

    @router.get("/whatsapp/webhook")
    async def verify(request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
        if not valid_handshake(settings.verify_token, dict(request.query_params)):
            raise HTTPException(status_code=403)
        return Response(request.query_params.get("hub.challenge", ""), media_type="text/plain")

    @router.post("/whatsapp/webhook")
    async def webhook(request: Request, background: BackgroundTasks) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        raw = await request.body()
        if not valid_signature(settings.app_secret, raw, request.headers.get(SIGNATURE_HEADER, "")):
            raise HTTPException(status_code=401)
        try:
            payload = Payload.model_validate_json(raw)
        except ValidationError as error:
            raise HTTPException(status_code=400) from error
        for number, text in accepted(payload, settings, seen):
            background.add_task(reply, agent, sender, number, text)
        return {"ok": True}

    return router
