"""The tools this server offers. Replace the example catalogue with your own capability."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

MAX_RESULTS = 25


class Item(BaseModel):
    """One entry of the example catalogue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str


CATALOGUE: tuple[Item, ...] = (
    Item(id="a-1", title="Getting started"),
    Item(id="a-2", title="Deploying to AgentCore"),
    Item(id="b-1", title="Deploying to Kubernetes"),
)


def find_items(query: str, limit: int) -> list[Item]:
    """Return at most ``limit`` catalogue items whose title contains ``query`` (case-insensitive)."""
    needle = query.strip().lower()
    return [item for item in CATALOGUE if needle in item.title.lower()][:limit]


def get_item(item_id: str) -> Item:
    """Return one item or raise ``LookupError`` (the client sees a tool error, never a stack trace)."""
    for item in CATALOGUE:
        if item.id == item_id:
            return item
    raise LookupError("item not found")


def register(server: MCPServer) -> None:
    """Register the tools on ``server``. Every input is validated and every result is bounded."""

    @server.tool()
    def search_items(  # pyright: ignore[reportUnusedFunction]
        query: Annotated[str, Field(min_length=1, max_length=200, description="Text to look for in titles")],
        limit: Annotated[int, Field(ge=1, le=MAX_RESULTS, description="Maximum number of results")] = 10,
    ) -> list[Item]:
        """Search the catalogue by title."""
        return find_items(query, limit)

    @server.tool()
    def read_item(  # pyright: ignore[reportUnusedFunction]
        item_id: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")],
    ) -> Item:
        """Read one catalogue item by id."""
        return get_item(item_id)
