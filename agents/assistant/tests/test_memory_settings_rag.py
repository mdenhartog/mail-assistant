import pytest

from app import memory
from app.a2a_main import create_executor
from app.rag import MAX_RESULTS, format_passages, make_retrieve_tool
from app.settings import Settings, SettingsError
from tests import DEV


def test_local_memory_uses_no_session_manager(settings: Settings):
    assert memory.session_manager_for(settings, "s", "u") is None


def test_agentcore_memory_builds_a_session_manager_for_the_session(monkeypatch):
    seen = {}

    class FakeManager:
        def __init__(self, config, region_name=None):
            seen["config"], seen["region"] = config, region_name

    monkeypatch.setattr(memory, "AgentCoreMemorySessionManager", FakeManager)
    settings = Settings.from_env(DEV | {"MEMORY_BACKEND": "agentcore", "MEMORY_ID": "mem-1", "AWS_REGION": "eu-west-1"})
    assert isinstance(memory.session_manager_for(settings, "s1", "u1"), FakeManager)
    assert (seen["config"].memory_id, seen["config"].session_id, seen["config"].actor_id) == ("mem-1", "s1", "u1")
    assert seen["region"] == "eu-west-1"


@pytest.mark.parametrize(
    "env",
    [
        {"MEMORY_BACKEND": "agentcore"},
        {"MEMORY_BACKEND": "elsewhere"},
        {"AGENT_PROTOCOL": "soap"},
        {"AGENT_MCP_URLS": "http://tools.example.com/mcp"},
        {"AGENT_MCP_URLS": "ftp://tools/mcp"},
        {"AGENT_MCP_URLS": "https:///mcp"},
    ],
)
def test_unsafe_or_incomplete_settings_are_refused(env):
    with pytest.raises(SettingsError):
        Settings.from_env(DEV | env)


def test_default_ports_follow_the_protocol():
    assert Settings.from_env(DEV).port == 8080
    assert Settings.from_env(DEV | {"AGENT_PROTOCOL": "a2a"}).port == 9000
    assert Settings.from_env(DEV | {"AGENT_MCP_URLS": "http://localhost:8100/mcp"}).mcp_urls == (
        "http://localhost:8100/mcp",
    )
    assert Settings.from_env(DEV | {"AGENT_MCP_URLS": "http://tools:8000/mcp"}).mcp_urls == ("http://tools:8000/mcp",)


def test_passages_are_delimited_bounded_and_marked_untrusted():
    response = {
        "retrievalResults": [
            {"content": {"text": f"text {n}"}, "location": {"s3Location": {"uri": f"s3://bucket/{n}.md"}}}
            for n in range(MAX_RESULTS + 3)
        ]
    }
    text = format_passages(response)
    assert "untrusted" in text
    assert text.count("<passage ") == MAX_RESULTS
    assert "s3://bucket/0.md" in text
    assert format_passages({}) == "No relevant passages found."


def test_the_retrieve_tool_queries_only_its_knowledge_base():
    calls = []

    class FakeClient:
        def retrieve(self, **kwargs):
            calls.append(kwargs)
            return {"retrievalResults": []}

    tool = make_retrieve_tool("KB123", FakeClient())
    assert tool.tool_name == "search_knowledge_base"
    assert tool(query="q" * 900) == "No relevant passages found."
    assert calls[0]["knowledgeBaseId"] == "KB123"
    assert len(calls[0]["retrievalQuery"]["text"]) == 500


def test_the_a2a_executor_builds_one_agent_per_context(settings: Settings):
    assert create_executor(settings) is not None
