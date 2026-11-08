"""A2A entry point (Agent2Agent protocol): other agents call this one (AgentCore contract: port 9000)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import uvicorn
from bedrock_agentcore.runtime import serve_a2a
from bedrock_agentcore.runtime.a2a import build_a2a_app
from strands.multiagent.a2a.executor import StrandsA2AExecutor

from app.agent import build_agent
from app.auth import BearerAuthMiddleware
from app.settings import BIND_HOST

if TYPE_CHECKING:
    from starlette.types import ASGIApp

    from app.settings import Settings

AGENT_CARD_PATH = "/.well-known/agent-card.json"  # discovery: the card holds no secrets and stays open


def create_executor(settings: Settings) -> StrandsA2AExecutor:
    """One agent per A2A context id, so callers never share a conversation."""
    return StrandsA2AExecutor(agent_factory=lambda context_id: build_agent(settings, context_id, "a2a-caller"))


def create_app(settings: Settings) -> ASGIApp:
    """The A2A app behind the bearer-token check (self-hosted); on AgentCore the platform authenticates instead."""
    app: ASGIApp = build_a2a_app(create_executor(settings), None, runtime_url=f"http://localhost:{settings.port}/")
    if settings.auth_mode == "token":
        return BearerAuthMiddleware(app, settings.auth_token, open_paths=frozenset({"/ping", AGENT_CARD_PATH}))
    return app


def main(settings: Settings) -> None:
    """Serve the agent card and the JSON-RPC endpoint at /."""
    if settings.auth_mode == "token":
        uvicorn.run(create_app(settings), host=BIND_HOST, port=settings.port, log_level="info")
    else:
        serve_a2a(create_executor(settings), port=settings.port)
