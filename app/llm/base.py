from typing import Any, Protocol


class LLMProvider(Protocol):
    """A single chat round-trip.

    Returns a dict with either:
      {"content": str}                         -- a final answer, or
      {"tool_calls": [{"name", "arguments"}]}  -- requests to run tools.
    May also include "assistant_message": the raw provider message, which the
    agent loop appends to history so multi-turn tool calling stays well-formed.
    """

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...
