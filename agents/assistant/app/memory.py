"""Conversation memory: where the agent remembers a session, and how many sessions it keeps in memory.

``local``: the Agent object keeps the conversation (development, tests, single instance).
``agentcore``: Amazon Bedrock AgentCore Memory keeps it (short-term events plus long-term records), so any instance
can continue any session. Switch with MEMORY_BACKEND and MEMORY_ID; the agent code does not change.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

if TYPE_CHECKING:
    from collections.abc import Callable

    from strands import Agent
    from strands.session import SessionManager

    from app.settings import Settings


def session_manager_for(settings: Settings, session_id: str, actor_id: str) -> SessionManager | None:
    """Return the session manager for this session, or ``None`` when the Agent object keeps the history itself."""
    if settings.memory_backend != "agentcore" or settings.memory_id is None:
        return None
    config = AgentCoreMemoryConfig(memory_id=settings.memory_id, session_id=session_id, actor_id=actor_id)
    return AgentCoreMemorySessionManager(config, region_name=settings.region)


class AgentPool:
    """A bounded least-recently-used set of agents, one per session; sessions never share an agent."""

    def __init__(self, factory: Callable[[str, str], Agent], max_sessions: int) -> None:
        """``factory(session_id, actor_id)`` builds an agent; sessions beyond ``max_sessions`` evict the oldest."""
        self._factory = factory
        self._max = max(1, max_sessions)
        self._agents: OrderedDict[tuple[str, str], Agent] = OrderedDict()

    def get(self, session_id: str, actor_id: str) -> Agent:
        """Return the agent of this (session, actor) pair, creating it on first use."""
        key = (session_id, actor_id)
        if key in self._agents:
            self._agents.move_to_end(key)
            return self._agents[key]
        agent = self._factory(session_id, actor_id)
        self._agents[key] = agent
        while len(self._agents) > self._max:
            self._agents.popitem(last=False)
        return agent

    def __len__(self) -> int:
        """Number of sessions currently held."""
        return len(self._agents)
