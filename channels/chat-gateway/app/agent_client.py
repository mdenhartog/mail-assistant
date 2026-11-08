"""How the gateway talks to the agent: plain HTTP (Docker, Kubernetes) or AgentCore Runtime (AWS). Same contract."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Protocol

import httpx2

SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"
MIN_SESSION_ID = 33  # AgentCore Runtime requires runtime session ids of at least 33 characters
HTTP_OK = 200


class AgentError(RuntimeError):
    """The agent did not answer. The message never contains the prompt or the answer."""


async def post_json(http: httpx2.AsyncClient, url: str, what: str, **kwargs: Any) -> httpx2.Response:  # noqa: ANN401
    """POST, and turn every transport failure into an AgentError that never names the URL (it may hold a token)."""
    try:
        return await http.post(url, **kwargs)
    except httpx2.HTTPError:
        raise AgentError(f"{what} unreachable or timed out") from None


class AgentClient(Protocol):
    """Anything that can answer a prompt for a session."""

    async def ask(self, prompt: str, session_id: str, actor_id: str) -> str:
        """Return the agent's answer."""
        ...


class InvokeClient(Protocol):
    """The part of the boto3 ``bedrock-agentcore`` client used here."""

    def invoke_agent_runtime(self, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
        """Call InvokeAgentRuntime."""
        ...


def runtime_session_id(channel: str, chat_id: str) -> str:
    """A stable session id per chat (memory continues across messages), at least 33 characters long."""
    digest = hashlib.sha256(f"{channel}:{chat_id}".encode()).hexdigest()
    return f"{channel}-{digest}"[: max(MIN_SESSION_ID, len(channel) + 1 + 32)]


class HttpAgentClient:
    """Calls ``POST {base_url}/invocations`` of an agent in this project or elsewhere."""

    def __init__(self, http: httpx2.AsyncClient, base_url: str, token: str | None, timeout: float) -> None:
        """``token`` is sent as a bearer token when the agent sits behind one."""
        self._http = http
        self._url = f"{base_url}/invocations"
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._timeout = timeout

    async def ask(self, prompt: str, session_id: str, actor_id: str) -> str:
        """Send the prompt; raise ``AgentError`` on any failure."""
        response = await post_json(
            self._http,
            self._url,
            "agent",
            json={"prompt": prompt, "session_id": session_id, "actor_id": actor_id},
            headers=self._headers | {SESSION_HEADER: session_id},
            timeout=self._timeout,
        )
        if response.status_code != HTTP_OK:
            raise AgentError(f"agent answered {response.status_code}")
        try:
            return str(response.json().get("response", ""))
        except ValueError:
            raise AgentError("agent answered with something that is not JSON") from None


class AgentCoreClient:
    """Calls an agent hosted on AgentCore Runtime with the caller's AWS credentials (SigV4)."""

    def __init__(self, client: InvokeClient, runtime_arn: str) -> None:
        """``client`` is ``boto3.client("bedrock-agentcore")``."""
        self._client = client
        self._arn = runtime_arn

    async def ask(self, prompt: str, session_id: str, actor_id: str) -> str:
        """Invoke the runtime in a worker thread (boto3 is blocking)."""
        payload = json.dumps({"prompt": prompt, "session_id": session_id, "actor_id": actor_id}).encode()
        try:
            result = await asyncio.to_thread(
                self._client.invoke_agent_runtime,
                agentRuntimeArn=self._arn,
                runtimeSessionId=session_id,
                payload=payload,
            )
            body = await asyncio.to_thread(result["response"].read)
        except Exception as error:  # boto raises many types; none may leak the payload
            raise AgentError("agent invocation failed") from error
        return str(json.loads(body).get("response", ""))
