from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tavern.llm.adapter import LLMConfig, LLMRegistry
from tavern.llm.anthropic_llm import AnthropicAdapter, _split_system
from tavern.world.models import ActionRequest
from tavern.engine.actions import ActionType


# ── _split_system helper ───────────────────────────────────────────────────

def test_split_system_no_system_messages():
    messages = [{"role": "user", "content": "hello"}]
    system, remaining = _split_system(messages)
    assert system == ""
    assert remaining == messages


def test_split_system_single_system_message():
    messages = [
        {"role": "system", "content": "You are a bartender."},
        {"role": "user", "content": "hello"},
    ]
    system, remaining = _split_system(messages)
    assert system == "You are a bartender."
    assert remaining == [{"role": "user", "content": "hello"}]


def test_split_system_multiple_system_messages_joined():
    messages = [
        {"role": "system", "content": "Part A."},
        {"role": "system", "content": "Part B."},
        {"role": "user", "content": "hello"},
    ]
    system, remaining = _split_system(messages)
    assert system == "Part A.\nPart B."
    assert len(remaining) == 1


# ── AnthropicAdapter.complete() ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_returns_text():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="The tavern is dark.")]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    result = await adapter.complete([{"role": "user", "content": "describe"}])
    assert result == "The tavern is dark."


@pytest.mark.asyncio
async def test_complete_with_response_format_returns_parsed_model():
    json_str = '{"action": "move", "target": "cellar", "detail": "go down", "confidence": 0.9}'
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json_str)]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    result = await adapter.complete(
        [{"role": "user", "content": "go cellar"}],
        response_format=ActionRequest,
    )
    assert isinstance(result, ActionRequest)
    assert result.action == ActionType.MOVE
    assert result.target == "cellar"


@pytest.mark.asyncio
async def test_complete_with_response_format_appends_json_instruction():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"action": "look", "confidence": 1.0}')]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    messages = [
        {"role": "system", "content": "You are a game assistant."},
        {"role": "user", "content": "look around"},
    ]
    await adapter.complete(messages, response_format=ActionRequest)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "Respond with valid JSON only." in call_kwargs["system"]


@pytest.mark.asyncio
async def test_complete_no_system_omits_system_kwarg():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    await adapter.complete([{"role": "user", "content": "hi"}])

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "system" not in call_kwargs


@pytest.mark.asyncio
async def test_complete_response_format_no_system_still_passes_system_kwarg():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"action": "look", "confidence": 1.0}')]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    # No system message in input
    await adapter.complete([{"role": "user", "content": "look"}], response_format=ActionRequest)

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs.get("system") == "Respond with valid JSON only."


# ── AnthropicAdapter.stream() ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_yields_chunks():
    async def fake_text_stream():
        yield "Hello"
        yield " world"

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_stream_ctx.text_stream = fake_text_stream()

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    chunks = []
    async for chunk in adapter.stream([{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_stream_with_system_passes_system_kwarg():
    async def fake_text_stream():
        yield "chunk"

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_stream_ctx.text_stream = fake_text_stream()

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)

    adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307"))
    adapter._client = mock_client

    chunks = []
    async for chunk in adapter.stream([
        {"role": "system", "content": "You are a narrator."},
        {"role": "user", "content": "describe"},
    ]):
        chunks.append(chunk)

    call_kwargs = mock_client.messages.stream.call_args.kwargs
    assert call_kwargs.get("system") == "You are a narrator."
    assert all(m["role"] != "system" for m in call_kwargs["messages"])


# ── API key / registry ─────────────────────────────────────────────────────

def test_api_key_env_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-123")
    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value = MagicMock()
        adapter = AnthropicAdapter(config=LLMConfig(provider="anthropic", model="claude-3-haiku-20240307", api_key=None))
    call_kwargs = mock_cls.call_args.kwargs
    assert call_kwargs["api_key"] == "env-key-123"


def test_registry_registers_anthropic():
    config = LLMConfig(provider="anthropic", model="claude-3-haiku-20240307", api_key="test")
    with patch("anthropic.AsyncAnthropic"):
        adapter = LLMRegistry.create(config)
    assert isinstance(adapter, AnthropicAdapter)


def test_anthropic_registered_after_import():
    """Importing anthropic_llm registers 'anthropic' in the global registry."""
    import importlib
    import tavern.llm.anthropic_llm  # noqa: F401
    importlib.reload(tavern.llm.anthropic_llm)  # force re-registration
    assert "anthropic" in LLMRegistry._providers
