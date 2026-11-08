"""Test doubles: no network, no AWS."""

from app.agent_client import AgentError


class FakeAgent:
    """Answers with ``reply`` (or fails); records every call."""

    def __init__(self, reply: str = "hello back", fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.calls: list[tuple[str, str, str]] = []

    async def ask(self, prompt: str, session_id: str, actor_id: str) -> str:
        self.calls.append((prompt, session_id, actor_id))
        if self.fail:
            raise AgentError("down")
        return self.reply


class FakeSender:
    """Collects what would have been sent."""

    def __init__(self) -> None:
        self.sent: list[tuple[object, str]] = []

    async def send(self, to, text: str) -> None:
        self.sent.append((to, text))
