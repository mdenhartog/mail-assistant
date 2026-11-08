"""A model that answers with a fixed text, so tests never call a real model."""

from collections.abc import AsyncIterator
from typing import Any

from strands.models import Model


class ScriptedModel(Model):
    """Streams ``reply`` and stops; records the prompts it was given."""

    def __init__(self, reply: str = "pong") -> None:
        self.reply = reply
        self.config: dict[str, Any] = {"model_id": "scripted"}
        self.calls = 0

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> Any:
        return self.config

    async def structured_output(self, output_model: Any, prompt: Any, system_prompt: Any = None, **kwargs: Any) -> Any:
        raise NotImplementedError
        yield

    async def stream(
        self, messages: Any, tool_specs: Any = None, system_prompt: Any = None, **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]:
        self.calls += 1
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": self.reply}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
