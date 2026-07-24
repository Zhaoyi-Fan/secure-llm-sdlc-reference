import json
from typing import Any

import httpx

from ..config import settings

_MAX_TOOL_CALLS_PER_RESPONSE = 16
_MAX_ARGUMENT_BYTES = 4_096


def _invalid_response(response: httpx.Response) -> httpx.RequestError:
    return httpx.RequestError(
        "local model returned an invalid response",
        request=response.request,
    )


class OpenAICompatibleProvider:
    """OpenAI-compatible local inference, validated with LM Studio."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (
            base_url or settings.openai_compatible_base_url
        ).rstrip("/")
        self.model = model or settings.openai_compatible_model
        self.api_key = (
            settings.openai_compatible_api_key if api_key is None else api_key
        )
        self.transport = transport

    @staticmethod
    def _serialize_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role in {"system", "user"}:
                if not isinstance(content, str):
                    raise httpx.HTTPError("invalid internal model history")
                serialized.append({"role": role, "content": content})
                continue

            if role == "assistant":
                calls = message.get("tool_calls")
                if not isinstance(calls, list) or not calls:
                    if not isinstance(content, str):
                        raise httpx.HTTPError("invalid internal model history")
                    serialized.append({"role": "assistant", "content": content})
                    continue

                wire_calls: list[dict[str, Any]] = []
                for call in calls:
                    if not isinstance(call, dict):
                        raise httpx.HTTPError("invalid internal model history")
                    function = call.get("function")
                    call_id = call.get("id")
                    if (
                        not isinstance(function, dict)
                        or not isinstance(call_id, str)
                        or not call_id
                    ):
                        raise httpx.HTTPError("invalid internal model history")
                    name = function.get("name")
                    arguments = function.get("arguments")
                    if not isinstance(name, str) or not isinstance(arguments, dict):
                        raise httpx.HTTPError("invalid internal model history")
                    wire_calls.append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(
                                    arguments,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            },
                        }
                    )
                serialized.append(
                    {
                        "role": "assistant",
                        "content": content if isinstance(content, str) and content else None,
                        "tool_calls": wire_calls,
                    }
                )
                continue

            if role == "tool":
                call_id = message.get("tool_call_id")
                if not isinstance(call_id, str) or not call_id:
                    raise httpx.HTTPError("invalid internal model history")
                if not isinstance(content, str):
                    raise httpx.HTTPError("invalid internal model history")
                serialized.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": content,
                    }
                )
                continue

            raise httpx.HTTPError("invalid internal model history")
        return serialized

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._serialize_messages(messages),
            "stream": False,
            "temperature": 0,
            "max_tokens": settings.openai_compatible_max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        timeout = httpx.Timeout(connect=5, read=300, write=10, pool=5)
        with httpx.Client(
            timeout=timeout,
            trust_env=False,
            transport=self.transport,
        ) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            raise _invalid_response(response) from exc

        if not isinstance(data, dict):
            raise _invalid_response(response)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise _invalid_response(response)
        choice = choices[0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise _invalid_response(response)
        message = choice["message"]
        tool_calls = message.get("tool_calls")

        if tool_calls is not None and not isinstance(tool_calls, list):
            raise _invalid_response(response)
        if tool_calls:
            if len(tool_calls) > _MAX_TOOL_CALLS_PER_RESPONSE:
                raise _invalid_response(response)
            normalized_calls: list[dict[str, Any]] = []
            for call in tool_calls:
                if not isinstance(call, dict) or not isinstance(
                    call.get("function"),
                    dict,
                ):
                    raise _invalid_response(response)
                function = call["function"]
                name = function.get("name")
                raw_arguments = function.get("arguments", "{}")
                if not isinstance(name, str) or not name:
                    raise _invalid_response(response)
                if isinstance(raw_arguments, str):
                    if len(raw_arguments.encode("utf-8")) > _MAX_ARGUMENT_BYTES:
                        raise _invalid_response(response)
                    try:
                        arguments = json.loads(raw_arguments or "{}")
                    except json.JSONDecodeError as exc:
                        raise _invalid_response(response) from exc
                else:
                    arguments = raw_arguments
                if not isinstance(arguments, dict):
                    raise _invalid_response(response)
                call_id = call.get("id")
                normalized_calls.append(
                    {
                        "id": call_id if isinstance(call_id, str) else "",
                        "name": name,
                        "arguments": arguments,
                    }
                )
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise _invalid_response(response)
            return {
                "content": content or "",
                "tool_calls": normalized_calls,
            }

        content = message.get("content")
        if not isinstance(content, str):
            raise _invalid_response(response)
        return {"content": content}
