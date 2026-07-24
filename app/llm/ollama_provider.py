import json
from typing import Any

import httpx

from ..config import settings


class OllamaProvider:
    """Talks to a local Ollama server (http://localhost:11434 by default)."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._serialize_messages(messages),
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        timeout = httpx.Timeout(connect=5, read=120, write=10, pool=5)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(f"{self.base_url}/api/chat", json=payload)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            raise httpx.RequestError(
                "local model returned invalid JSON",
                request=resp.request,
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
            raise httpx.RequestError(
                "local model returned an invalid response",
                request=resp.request,
            )
        message = data["message"]
        tool_calls = message.get("tool_calls")
        if tool_calls is not None and not isinstance(tool_calls, list):
            raise httpx.RequestError(
                "local model returned an invalid response",
                request=resp.request,
            )
        if tool_calls:
            normalized_calls: list[dict[str, Any]] = []
            for tc in tool_calls:
                if not isinstance(tc, dict) or not isinstance(
                    tc.get("function"),
                    dict,
                ):
                    raise httpx.RequestError(
                        "local model returned an invalid response",
                        request=resp.request,
                    )
                function = tc["function"]
                name = function.get("name")
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments or "{}")
                    except json.JSONDecodeError as exc:
                        raise httpx.RequestError(
                            "local model returned an invalid response",
                            request=resp.request,
                        ) from exc
                if not isinstance(name, str) or not isinstance(arguments, dict):
                    raise httpx.RequestError(
                        "local model returned an invalid response",
                        request=resp.request,
                    )
                normalized_calls.append(
                    {
                        "id": tc.get("id", ""),
                        "name": name,
                        "arguments": arguments,
                    }
                )
            return {
                "content": message.get("content") or "",
                "tool_calls": normalized_calls,
            }
        content = message.get("content")
        if not isinstance(content, str):
            raise httpx.RequestError(
                "local model returned an invalid response",
                request=resp.request,
            )
        return {"content": content}

    @staticmethod
    def _serialize_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role == "assistant" and message.get("tool_calls"):
                calls = message["tool_calls"]
                serialized.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": call["function"]["name"],
                                    "arguments": call["function"]["arguments"],
                                }
                            }
                            for call in calls
                        ],
                    }
                )
            elif role == "tool":
                serialized.append(
                    {
                        "role": "tool",
                        "tool_name": message.get("tool_name", ""),
                        "content": content,
                    }
                )
            else:
                serialized.append({"role": role, "content": content})
        return serialized
