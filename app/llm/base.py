from typing import Any, Protocol


class LLMProvider(Protocol):
    """A single chat round-trip.

    Returns a dict with either:
      {"content": str}                         -- a final answer, or
      {"tool_calls": [{"id", "name", "arguments"}]} -- normalized tool requests.

    Provider adapters translate between the agent's provider-neutral history
    and their native wire format. Raw provider messages are never replayed.
    """

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...
