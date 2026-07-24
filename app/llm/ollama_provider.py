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
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        message = resp.json().get("message", {})
        tool_calls = message.get("tool_calls")
        if tool_calls:
            return {
                "tool_calls": [
                    {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"].get("arguments", {}),
                    }
                    for tc in tool_calls
                ],
                "assistant_message": message,
            }
        return {"content": message.get("content", ""), "assistant_message": message}
