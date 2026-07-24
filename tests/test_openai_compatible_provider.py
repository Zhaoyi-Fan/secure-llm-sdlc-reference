import json
from typing import Any

import httpx
import pytest

from app.agent import run_agent
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_compatible_provider import OpenAICompatibleProvider


def test_openai_compatible_provider_parses_tool_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert payload["model"] == "qwen/qwen3.6-27b"
        assert payload["tool_choice"] == "auto"
        assert payload["temperature"] == 0
        assert payload["tools"][0]["function"]["name"] == "list_my_orders"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "server-call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "list_my_orders",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:1234/v1",
        model="qwen/qwen3.6-27b",
        api_key="",
        transport=httpx.MockTransport(handler),
    )
    result = provider.chat(
        [{"role": "user", "content": "List my orders"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "list_my_orders",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    assert result == {
        "content": "",
        "tool_calls": [
            {
                "id": "server-call-1",
                "name": "list_my_orders",
                "arguments": {},
            }
        ],
    }


def test_provider_serializers_preserve_native_tool_history_contracts() -> None:
    internal = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "list"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "list_my_orders",
                        "arguments": {},
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "tool_name": "list_my_orders",
            "content": '{"data":[]}',
        },
    ]

    openai_messages = OpenAICompatibleProvider._serialize_messages(internal)
    assert openai_messages[2]["tool_calls"][0]["id"] == "call-1"
    assert openai_messages[2]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert openai_messages[3] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"data":[]}',
    }

    ollama_messages = OllamaProvider._serialize_messages(internal)
    assert "id" not in ollama_messages[2]["tool_calls"][0]
    assert ollama_messages[2]["tool_calls"][0]["function"]["arguments"] == {}
    assert ollama_messages[3] == {
        "role": "tool",
        "tool_name": "list_my_orders",
        "content": '{"data":[]}',
    }


@pytest.mark.parametrize(
    "arguments",
    ["not-json", "[1, 2, 3]"],
)
def test_openai_compatible_provider_rejects_invalid_tool_arguments(
    arguments: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "bad-call",
                                    "type": "function",
                                    "function": {
                                        "name": "search_kb",
                                        "arguments": arguments,
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            request=request,
        )

    provider = OpenAICompatibleProvider(
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.HTTPError, match="invalid response"):
        provider.chat([{"role": "user", "content": "search"}])


def test_openai_compatible_provider_propagates_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal detail", request=request)

    provider = OpenAICompatibleProvider(
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError):
        provider.chat([{"role": "user", "content": "hello"}])


def test_openai_compatible_provider_accepts_empty_tool_call_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Final answer",
                            "tool_calls": [],
                        }
                    }
                ]
            },
            request=request,
        )

    provider = OpenAICompatibleProvider(
        transport=httpx.MockTransport(handler),
    )
    assert provider.chat([{"role": "user", "content": "hello"}]) == {
        "content": "Final answer"
    }


class CorrelationAssertingProvider:
    def __init__(self) -> None:
        self.step = 0

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
                        "id": "duplicate",
                        "name": "list_my_orders",
                        "arguments": {},
                    },
                    {
                        "id": "duplicate",
                        "name": "search_kb",
                        "arguments": {"query": "Refund policy"},
                    },
                ]
            }

        assistant = messages[-3]
        first_tool = messages[-2]
        second_tool = messages[-1]
        call_ids = [call["id"] for call in assistant["tool_calls"]]
        assert len(call_ids) == len(set(call_ids)) == 2
        assert first_tool["tool_call_id"] == call_ids[0]
        assert second_tool["tool_call_id"] == call_ids[1]
        return {"content": "Correlation preserved."}


def test_agent_assigns_unique_matching_tool_call_ids(
    isolated_db,
    ids: dict[str, int],
) -> None:
    del isolated_db
    result = run_agent(
        "List orders and search the refund policy.",
        ids["user:alice"],
        provider=CorrelationAssertingProvider(),
        include_trace=True,
    )
    assert result["reply"] == "Correlation preserved."
    assert [entry["tool"] for entry in result["trace"]] == [
        "list_my_orders",
        "search_kb",
    ]
