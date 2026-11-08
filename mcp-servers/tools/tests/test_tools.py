import pytest
from mcp.client import Client

from app.server import build_server
from app.tools import MAX_RESULTS, find_items, get_item


def test_find_items_matches_case_insensitively_and_respects_the_limit():
    assert [i.id for i in find_items("DEPLOYING", 10)] == ["a-2", "b-1"]
    assert len(find_items("deploying", 1)) == 1


def test_get_item_unknown_raises_lookup_error():
    with pytest.raises(LookupError):
        get_item("zzz")


async def test_the_server_lists_exactly_its_tools():
    async with Client(build_server()) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
    assert names == {"search_items", "read_item"}


async def test_search_returns_results():
    async with Client(build_server()) as client:
        result = await client.call_tool("search_items", {"query": "kubernetes"})
    assert not result.is_error
    assert "b-1" in str(result.content)


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("search_items", {"query": ""}),
        ("search_items", {"query": "x", "limit": MAX_RESULTS + 1}),
        ("read_item", {"item_id": "../etc/passwd"}),
    ],
)
async def test_invalid_input_is_rejected(tool: str, arguments: dict[str, object]):
    async with Client(build_server()) as client:
        result = await client.call_tool(tool, arguments)
    assert result.is_error


async def test_unknown_item_is_a_tool_error_without_a_stack_trace():
    async with Client(build_server()) as client:
        result = await client.call_tool("read_item", {"item_id": "nope"})
    assert result.is_error
    assert "Traceback" not in str(result.content)
