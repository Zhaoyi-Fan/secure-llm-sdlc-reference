import json
from typing import Any

from . import tools
from .llm.base import LLMProvider
from .llm.ollama_provider import OllamaProvider

SYSTEM_PROMPT = (
    "You are SupportAssist, a customer-support assistant for an online store. "
    "Help the signed-in customer with their orders, refunds and questions. "
    "Use the provided tools to look up real data. Be concise and friendly."
)

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_my_orders",
            "description": "List the signed-in customer's orders.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Get details for one order by its numeric id.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "integer"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "issue_refund",
            "description": "Issue a refund for an order, in cents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer"},
                    "amount_cents": {"type": "integer"},
                },
                "required": ["order_id", "amount_cents"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "Search the help-center knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]


def _dispatch(name: str, args: dict[str, Any], current_user_id: int) -> Any:
    # The caller's identity comes from the session, never from the model.
    if name == "list_my_orders":
        return tools.list_my_orders(current_user_id)
    if name == "get_order":
        return tools.get_order(int(args["order_id"]), current_user_id)
    if name == "issue_refund":
        return tools.issue_refund(int(args["order_id"]), int(args["amount_cents"]), current_user_id)
    if name == "search_kb":
        return tools.search_kb(str(args["query"]))
    return {"error": f"unknown tool {name}"}


def run_agent(
    user_message: str,
    current_user_id: int,
    provider: LLMProvider | None = None,
    max_steps: int = 5,
) -> dict[str, Any]:
    provider = provider or OllamaProvider()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    trace: list[dict[str, Any]] = []
    for _ in range(max_steps):
        result = provider.chat(messages, tools=TOOL_SCHEMAS)
        if "tool_calls" in result:
            # Keep the assistant's tool-call turn in history before the tool
            # results; otherwise the chat template sees user -> tool and breaks.
            messages.append(
                result.get("assistant_message")
                or {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": c["name"], "arguments": c.get("arguments", {})}}
                        for c in result["tool_calls"]
                    ],
                }
            )
            for call in result["tool_calls"]:
                try:
                    output = _dispatch(call["name"], call.get("arguments", {}), current_user_id)
                except Exception as exc:  # feed the error back so the model can recover
                    output = {"error": f"{type(exc).__name__}: {exc}"}
                trace.append(
                    {"tool": call["name"], "arguments": call.get("arguments", {}), "output": output}
                )
                messages.append(
                    {"role": "tool", "tool_name": call["name"], "content": json.dumps(output, default=str)}
                )
            continue
        return {"reply": result.get("content", ""), "trace": trace}
    return {"reply": "(stopped: max steps reached)", "trace": trace}
