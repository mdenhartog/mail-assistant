"""Builds the MCP server and the ASGI app around it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.mcpserver import MCPServer
from starlette.responses import JSONResponse

from app.auth import BearerAuthMiddleware
from app.settings import BIND_HOST
from app.tools import register

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.types import ASGIApp

    from app.settings import Settings


def build_server() -> MCPServer:
    """Create the MCP server with its tools."""
    server = MCPServer("tools", instructions="Tools of the tools service.")
    register(server)
    return server


async def ping(_request: Request) -> JSONResponse:
    """Health endpoint; AgentCore Runtime and Kubernetes probes expect a 2xx with a JSON body."""
    return JSONResponse({"status": "Healthy"})


def create_app(settings: Settings, server: MCPServer | None = None) -> ASGIApp:
    """Streamable-HTTP app: stateless (scales horizontally), JSON responses, ``/mcp`` plus ``/ping``."""
    mcp_server = server or build_server()
    app = mcp_server.streamable_http_app(stateless_http=True, json_response=True, host=BIND_HOST)
    app.add_route("/ping", ping, methods=["GET"])
    if settings.auth_mode == "token":
        return BearerAuthMiddleware(app, settings.auth_token)
    return app
