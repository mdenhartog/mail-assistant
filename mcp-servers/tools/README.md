# tools (MCP server)

Streamable HTTP MCP server on port 8000 (`/mcp`, health `/ping`). The same container runs on Docker Desktop, Kubernetes and AWS AgentCore Runtime (protocol `MCP`).

- Tools: `app/tools.py` (replace the example catalogue; every input validated, every result bounded).
- Auth: `MCP_AUTH_MODE=token` (default, needs `MCP_AUTH_TOKEN` of 32+ characters), `platform` (AgentCore authenticates before the request reaches the container) or `off` (development only).
- Test: `uv run pytest` · run: `uv run python -m app` · image: `docker build .` (AgentCore needs `--platform linux/arm64`).
