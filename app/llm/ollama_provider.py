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
        timeout = httpx.Timeout(connect=5, read=120, write=10, pool=5)
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(f"{self.base_url}/api/chat", json=payload)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            raise httpx.HTTPError(
                "local model returned invalid JSON",
                request=resp.request,
            ) from exc
        if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
            raise httpx.HTTPError(
                "local model returned an invalid response",
                request=resp.request,
            )
        message = data["message"]
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
