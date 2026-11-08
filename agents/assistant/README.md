# assistant (agent)

A Strands agent served with the AgentCore runtime contract: `POST /invocations` and `GET /ping` on port 8080 (`AGENT_PROTOCOL=http`), or an A2A server on port 9000 (`AGENT_PROTOCOL=a2a`). The same container runs on Docker Desktop, Kubernetes and AWS AgentCore Runtime.

| What | Where / how |
|---|---|
| Tools | `app/tools.py` (own tools) · `AGENT_MCP_URLS` (MCP servers) · `KNOWLEDGE_BASE_ID` (Bedrock Knowledge Base, RAG) |
| Memory | `MEMORY_BACKEND=local` (default) or `agentcore` + `MEMORY_ID` (AgentCore Memory) |
| Model | `AGENT_MODEL_ID` (default: the SDK default); other providers: change `build_model` in `app/agent.py` |
| Auth | `AGENT_AUTH_MODE=token` (default; `AGENT_AUTH_TOKEN`, 32+ characters), `platform` on AgentCore, `off` for development only |
| MCP on AgentCore | `AGENT_MCP_RUNTIME_ARNS` (SigV4; the CDK app sets it) |
| Request | `{"prompt": "...", "session_id": "...", "actor_id": "..."}`; the platform session header wins over the body |

Test: `uv run pytest` (a scripted model, no AWS calls) · run: `uv run python -m app` · image: `docker build .` (AgentCore needs `--platform linux/arm64`).
