"""Tests for DeepSeek integration and environment-driven agent assembly."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.kernel.factory import create_deepseek_agent
from app.kernel.model.deepseek import DeepSeekProvider


def test_settings_loads_deepseek_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("AGENT_MAX_STEPS", "12")

    settings = Settings()

    assert settings.deepseek_api_key == "test-key"
    assert settings.deepseek_model == "deepseek-chat"
    assert settings.agent_max_steps == 12


def test_factory_requires_api_key() -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        create_deepseek_agent(Settings(deepseek_api_key=None))


def test_factory_uses_environment_settings(tmp_path) -> None:
    settings = Settings(
        deepseek_api_key="test-key",
        deepseek_model="deepseek-chat",
        agent_system_prompt="测试 Agent",
        agent_max_steps=7,
        agent_max_tokens=800,
        agent_max_seconds=30,
    )

    orchestrator, environment = create_deepseek_agent(settings, workspace=tmp_path)

    assert orchestrator._default_settings.model == "deepseek-chat"
    assert orchestrator._default_settings.system_prompt == "测试 Agent"
    assert orchestrator._default_settings.budget.max_steps == 7
    assert environment._workspace == tmp_path.resolve()


@pytest.mark.asyncio
async def test_deepseek_provider_normalizes_response() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="我已读取文件。",
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(
                                name="read_file",
                                arguments='{"path":"README.md"}',
                            ),
                        )
                    ],
                )
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": response.choices[0].message.content,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path":"README.md"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )
    )
    provider = DeepSeekProvider(api_key="test-key")
    with patch(
        "app.kernel.model.deepseek.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport),
    ):
        result = await provider.complete(
            {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "读取 README"}],
                "tools": [],
            }
        )

    assert result["content"] == "我已读取文件。"
    assert result["tool_calls"][0]["function"]["name"] == "read_file"
    assert result["tool_calls"][0]["function"]["arguments"] == {"path": "README.md"}
    assert result["usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_provider_surfaces_api_error_body() -> None:
    """A 4xx must carry DeepSeek's explanation, not just the status line."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            400,
            json={
                "error": {
                    "message": "invalid type: map, expected a string at line 1 column 333",
                    "type": "invalid_request_error",
                }
            },
        )
    )
    provider = DeepSeekProvider(api_key="test-key")
    with patch(
        "app.kernel.model.deepseek.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport),
    ):
        with pytest.raises(ValueError, match="invalid type: map"):
            await provider.complete(
                {"model": "deepseek-chat", "messages": [], "tools": []}
            )


@pytest.mark.asyncio
async def test_provider_preserves_raw_message() -> None:
    """raw_message keeps the fields the API requires back on the next call."""
    raw = {
        "role": "assistant",
        "content": "",
        "reasoning_content": "thinking...",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"README.md"}'},
            }
        ],
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"choices": [{"message": raw}], "usage": {"total_tokens": 15}}
        )
    )
    provider = DeepSeekProvider(api_key="test-key")
    with patch(
        "app.kernel.model.deepseek.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport),
    ):
        result = await provider.complete(
            {"model": "deepseek-chat", "messages": [], "tools": []}
        )

    assert result["raw_message"] == raw
    # Normalized view still parses arguments for the kernel's tool executor.
    assert result["tool_calls"][0]["function"]["arguments"] == {"path": "README.md"}


@pytest.mark.asyncio
async def test_deepseek_provider_does_not_retry_auth_errors():
    response = httpx.Response(403, request=httpx.Request("POST", "https://example.test"))
    provider = DeepSeekProvider(
        api_key="test-key",
        base_url="https://example.test",
        max_retries=2,
    )

    with patch("app.kernel.model.deepseek.httpx.AsyncClient") as client_class:
        client = client_class.return_value.__aenter__.return_value
        client.post = AsyncMock(return_value=response)
        with pytest.raises(ValueError, match="permission denied"):
            await provider.complete({"messages": [{"role": "user", "content": "test"}]})
        assert client.post.await_count == 1
