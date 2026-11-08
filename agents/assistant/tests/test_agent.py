from app.agent import build_agent, build_tools
from app.memory import AgentPool
from app.settings import Settings
from app.tools import MAX_TEXT, word_count
from tests import DEV

from .fakes import ScriptedModel


def test_word_count_counts_and_is_bounded():
    assert word_count("one two  three") == 3
    assert word_count("a " * MAX_TEXT) <= MAX_TEXT // 2


def test_the_agent_answers_through_the_model(settings: Settings):
    model = ScriptedModel("pong")
    agent = build_agent(settings, "s1", "u1", model=model)
    assert str(agent("ping")).strip() == "pong"
    assert model.calls == 1


def test_the_local_tool_is_registered(settings: Settings):
    agent = build_agent(settings, "s1", "u1", model=ScriptedModel())
    assert "word_count" in agent.tool_names


def test_mcp_servers_become_tools_and_the_knowledge_base_is_optional(monkeypatch):
    configured = Settings.from_env(
        DEV | {"AGENT_MCP_URLS": "https://tools.example.com/mcp", "AGENT_MCP_TOKEN": "x" * 40}
    )
    assert len(build_tools(configured)) == 2
    assert len(build_tools(Settings.from_env(DEV))) == 1


def test_sessions_never_share_an_agent(settings: Settings):
    pool = AgentPool(lambda s, a: build_agent(settings, s, a, model=ScriptedModel()), max_sessions=2)
    first = pool.get("s1", "u1")
    assert pool.get("s1", "u1") is first
    assert pool.get("s2", "u1") is not first
    assert pool.get("s1", "u2") is not first


def test_the_pool_evicts_the_least_recently_used_session(settings: Settings):
    pool = AgentPool(lambda s, a: build_agent(settings, s, a, model=ScriptedModel()), max_sessions=2)
    first = pool.get("s1", "u")
    pool.get("s2", "u")
    pool.get("s1", "u")
    pool.get("s3", "u")
    assert len(pool) == 2
    assert pool.get("s1", "u") is first
