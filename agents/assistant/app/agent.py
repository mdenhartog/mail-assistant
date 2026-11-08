"""Builds the Strands agent: model, system prompt, local tools, MCP tools and the knowledge base tool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import boto3
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

from app.mcp_auth import SigV4, runtime_url
from app.memory import session_manager_for
from app.rag import RetrieveClient, make_retrieve_tool
from app.settings import RUNTIME_ARN
from app.tools import LOCAL_TOOLS

if TYPE_CHECKING:
    from strands.models import Model

    from app.settings import Settings


def build_model(settings: Settings) -> Model:
    """Amazon Bedrock by default; change this function to use another provider the SDK supports."""
    if settings.model_id:
        return BedrockModel(model_id=settings.model_id, region_name=settings.region)
    return BedrockModel(region_name=settings.region)


def mcp_clients(settings: Settings) -> list[MCPClient]:
    """One client per MCP server: bearer token for servers you host yourself, SigV4 for runtimes on AgentCore."""
    headers = {"Authorization": f"Bearer {settings.mcp_token}"} if settings.mcp_token else None
    clients = [MCPClient(url=url, headers=headers) for url in settings.mcp_urls]
    for arn in settings.mcp_runtime_arns:
        region = RUNTIME_ARN.match(arn)
        clients.append(MCPClient(url=runtime_url(arn), auth_provider=SigV4(region["region"] if region else "")))
    return clients


def build_tools(settings: Settings) -> list[Any]:
    """Local tools, the MCP clients and the knowledge base when configured."""
    tools: list[Any] = list(LOCAL_TOOLS)
    tools.extend(mcp_clients(settings))
    if settings.knowledge_base_id:
        client = cast("RetrieveClient", boto3.client("bedrock-agent-runtime", region_name=settings.region))
        tools.append(make_retrieve_tool(settings.knowledge_base_id, client))
    return tools


def build_agent(settings: Settings, session_id: str, actor_id: str, model: Model | None = None) -> Agent:
    """One agent for one session. ``model`` is injectable so tests never call a real model."""
    return Agent(
        name="assistant",
        model=model or build_model(settings),
        system_prompt=settings.system_prompt,
        tools=build_tools(settings),
        session_manager=session_manager_for(settings, session_id, actor_id),
        callback_handler=None,
    )
