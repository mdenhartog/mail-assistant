"""The gateway app: health plus one router per enabled channel."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

import boto3
import httpx2
from fastapi import FastAPI

from app import telegram, whatsapp
from app.agent_client import AgentClient, AgentCoreClient, HttpAgentClient, InvokeClient
from app.dedupe import SeenCache
from app.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def create_app(
    settings: Settings,
    agent: AgentClient,
    telegram_sender: telegram.TelegramSender | None = None,
    whatsapp_sender: whatsapp.WhatsAppSender | None = None,
    on_shutdown: httpx2.AsyncClient | None = None,
) -> FastAPI:
    """Build the app from injected parts (fakes in tests). ``on_shutdown`` is an HTTP client to close on exit."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        yield
        if on_shutdown is not None:
            await on_shutdown.aclose()

    app = FastAPI(title="chat-gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    seen = SeenCache()

    @app.get("/ping")
    async def ping() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "Healthy"}

    if settings.telegram and telegram_sender:
        app.include_router(telegram.build_router(settings.telegram, agent, telegram_sender, seen))
    if settings.whatsapp and whatsapp_sender:
        app.include_router(whatsapp.build_router(settings.whatsapp, agent, whatsapp_sender, seen))
    return app


def create_app_from_env() -> FastAPI:
    """Production wiring: real HTTP client, real senders, the agent backend chosen by AGENT_BACKEND."""
    settings = Settings.from_env()
    http = httpx2.AsyncClient(timeout=settings.reply_timeout)
    if settings.agent_backend == "agentcore" and settings.agent_runtime_arn:
        runtime = cast("InvokeClient", boto3.client("bedrock-agentcore", region_name=settings.region))
        agent: AgentClient = AgentCoreClient(runtime, settings.agent_runtime_arn)
    else:
        agent = HttpAgentClient(http, settings.agent_url or "", settings.agent_token, settings.reply_timeout)
    return create_app(
        settings,
        agent,
        telegram.HttpTelegramSender(http, settings.telegram.bot_token) if settings.telegram else None,
        whatsapp.HttpWhatsAppSender(http, settings.whatsapp) if settings.whatsapp else None,
        on_shutdown=http,
    )
