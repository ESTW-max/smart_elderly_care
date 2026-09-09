"""DeepSeek provider using its OpenAI-compatible HTTP API."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.kernel.model.interfaces import IModelProvider


class DeepSeekProvider(IModelProvider):
    """Call DeepSeek chat completion and normalize tool calls for the kernel."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required to use DeepSeekProvider")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout_seconds = timeout_seconds
        self._max_retries = max(0, max_retries)

    async def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send a completion request and return the kernel's common response shape."""
        payload: dict[str, Any] = {
            "model": request.get("model", self._model),
            "messages": request["messages"],
            "temperature": request.get("temperature", self._temperature),
            "max_tokens": request.get("max_tokens", self._max_tokens),
        }
        if request.get("tools"):
            payload["tools"] = request["tools"]

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                if response.status_code in {401, 403}:
                    raise ValueError(
                        "DeepSeek authentication or permission denied "
                        f"(HTTP {response.status_code})"
                    )
                if response.is_error:
                    raise ValueError(
                        f"DeepSeek API returned HTTP {response.status_code}: {response.text}"
                    )
                data = response.json()
                break
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                if attempt >= self._max_retries:
                    raise RuntimeError(
                        f"DeepSeek request failed after {attempt + 1} attempts: {exc}"
                    ) from exc
                await asyncio.sleep(2**attempt)
        else:
            raise RuntimeError(f"DeepSeek request failed: {last_error}") from last_error

        message = data["choices"][0]["message"]
        tool_calls: list[dict[str, Any]] = []
        for tool_call in message.get("tool_calls") or []:
            function = tool_call["function"]
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"DeepSeek returned invalid JSON for tool {function['name']}: {exc}"
                    ) from exc
            tool_calls.append(
                {
                    "id": tool_call["id"],
                    "type": tool_call.get("type", "function"),
                    "function": {
                        "name": function["name"],
                        "arguments": arguments,
                    },
                }
            )

        usage = data.get("usage") or {}
        return {
            "content": message.get("content") or "",
            "tool_calls": tool_calls,
            # Verbatim provider message, replayed as-is when rebuilding history.
            # Reconstructing it loses fields the API requires back (e.g.
            # reasoning_content on thinking models) and re-encodes
            # function.arguments as an object instead of a JSON string.
            "raw_message": message,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }
