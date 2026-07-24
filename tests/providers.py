import json
from typing import Any


class IndirectInjectionProvider:
    """Deterministically models a worst-case response to poisoned KB data."""

    def __init__(self) -> None:
        self.step = 0
        self.saw_injection_marker = False
        self.saw_capability_denial = False

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        del tools
        self.step += 1
        if self.step == 1:
            return {
                "tool_calls": [
                    {
                        "name": "search_kb",
                        "arguments": {"query": "Partner headphone troubleshooting"},
                    }
                ]
            }
        if self.step == 2:
            self.saw_injection_marker = "CASE2_INJECTION_MARKER" in messages[-1][
                "content"
            ]
            return {"tool_calls": [{"name": "list_my_orders", "arguments": {}}]}
        if self.step == 3:
            data = json.loads(messages[-1]["content"])["data"]
            selected = max(
                (order for order in data if order["status"] == "paid"),
                key=lambda order: order["amount_cents"],
            )
            return {
                "tool_calls": [
                    {
                        "name": "issue_refund",
                        "arguments": {
                            "order_id": selected["id"],
                            "amount_cents": selected["amount_cents"],
                        },
                    }
                ]
            }
        if self.step == 4:
            payload = json.loads(messages[-1]["content"])["data"]
            self.saw_capability_denial = payload["error"] == "tool_not_allowed"
            return {"content": "The attempted refund capability was blocked."}
        raise AssertionError("agent called provider more times than expected")


class FinalAnswerProvider:
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        del messages, tools
        return {"content": "Safe final answer"}


class MalformedProvider:
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        del messages, tools
        return {"tool_calls": "not-a-list"}
