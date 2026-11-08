"""HTTP entry point for AgentCore Runtime (``POST /invocations``, ``GET /ping``) and for any container platform."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.responses import JSONResponse

from app.agent import build_agent
from app.auth import BearerAuthMiddleware
from app.memory import AgentPool

if TYPE_CHECKING:
    from app.settings import Settings


class InvokeRequest(BaseModel):
    """The request body. Unknown fields are refused; the prompt length is bounded."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    actor_id: str | None = Field(default=None, min_length=1, max_length=128)


def create_app(settings: Settings, pool: AgentPool | None = None) -> BedrockAgentCoreApp:
    """The app. ``pool`` is injectable so tests use a scripted model instead of a real one."""
    agents = pool if pool is not None else AgentPool(lambda s, a: build_agent(settings, s, a), settings.max_sessions)
    app = BedrockAgentCoreApp()
    if settings.auth_mode == "token":  # self-hosted: only callers with the bearer token (the channel gateway) get in
        app.add_middleware(BearerAuthMiddleware, token=settings.auth_token)

    @app.entrypoint
    async def invoke(payload: dict[str, Any], context: RequestContext) -> Any:  # noqa: ANN401  # pyright: ignore[reportUnusedFunction]
        try:
            request = InvokeRequest.model_validate(payload)
        except ValidationError:
            return JSONResponse({"error": "invalid_request"}, status_code=422)
        if len(request.prompt) > settings.max_prompt_chars:
            return JSONResponse({"error": "prompt_too_long"}, status_code=413)
        # The platform's session id (header X-Amzn-Bedrock-AgentCore-Runtime-Session-Id) wins over the body.
        session_id = context.session_id or request.session_id or str(uuid4())
        actor_id = request.actor_id or "anonymous"
        result = await agents.get(session_id, actor_id).invoke_async(request.prompt)
        return {"response": str(result).strip(), "session_id": session_id}

    return app
