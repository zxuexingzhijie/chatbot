from __future__ import annotations

import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from tavern.llm.adapter import LLMConfig, LLMRegistry, LLMError
from tavern.world.models import ActionRequest
from tavern.engine.actions import ActionType


def test_append_json_instruction_modifies_last_system():
    from tavern.llm.ollama_llm import _append_json_instruction
    messages = [
        {"role": "system", "content": "First system."},
        {"role": "system", "content": "Second system."},
        {"role": "user", "content": "hello"},
    ]
    result = _append_json_instruction(messages)
    assert result[0] == {"role": "system", "content": "First system."}
    assert result[1]["content"].endswith("Respond with valid JSON only.")
    assert result[2] == {"role": "user", "content": "hello"}
    # Original not modified
    assert messages[1]["content"] == "Second system."


def test_append_json_instruction_no_system_inserts_one():
    from tavern.llm.ollama_llm import _append_json_instruction
    messages = [{"role": "user", "content": "hello"}]
    result = _append_json_instruction(messages)
    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert "Respond with valid JSON only." in result[0]["content"]
    assert result[1] == {"role": "user", "content": "hello"}


@pytest.mark.asyncio
async def test_complete_returns_text():
    from tavern.llm.ollama_llm import OllamaAdapter

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": {"content": "The tavern is dark."}}
    mock_response.raise_for_status = MagicMock()

    config = LLMConfig(provider="ollama", model="llama3:8b", max_retries=1)
    adapter = OllamaAdapter(config=config)
    adapter._client = AsyncMock()
    adapter._client.post = AsyncMock(return_value=mock_response)

    result = await adapter.complete([{"role": "user", "content": "describe"}])
    assert result == "The tavern is dark."


@pytest.mark.asyncio
async def test_complete_with_response_format_returns_parsed_model():
    from tavern.llm.ollama_llm import OllamaAdapter

    json_str = '{"action": "move", "target": "cellar", "detail": "go down", "confidence": 0.9}'
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": {"content": json_str}}
    mock_response.raise_for_status = MagicMock()

    config = LLMConfig(provider="ollama", model="llama3:8b", max_retries=1)
    adapter = OllamaAdapter(config=config)
    adapter._client = AsyncMock()
    adapter._client.post = AsyncMock(return_value=mock_response)

    result = await adapter.complete(
        [{"role": "user", "content": "go cellar"}],
        response_format=ActionRequest,
    )
    assert isinstance(result, ActionRequest)
    assert result.action == ActionType.MOVE


@pytest.mark.asyncio
async def test_complete_sets_json_format_when_response_format():
    from tavern.llm.ollama_llm import OllamaAdapter

    mock_response = MagicMock()
    mock_response.json.return_value = {"message": {"content": '{"action": "look", "confidence": 1.0}'}}
    mock_response.raise_for_status = MagicMock()

    config = LLMConfig(provider="ollama", model="llama3:8b", max_retries=1)
    adapter = OllamaAdapter(config=config)
    adapter._client = AsyncMock()
    adapter._client.post = AsyncMock(return_value=mock_response)

    await adapter.complete(
        [{"role": "system", "content": "You are a parser."}, {"role": "user", "content": "look"}],
        response_format=ActionRequest,
    )

    call_kwargs = adapter._client.post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert body["format"] == "json"


async def _async_lines(lines: list[str]):
    for line in lines:
        yield line


@pytest.mark.asyncio
async def test_stream_yields_chunks():
    from tavern.llm.ollama_llm import OllamaAdapter

    lines = [
        json.dumps({"message": {"content": "Hello"}, "done": False}),
        json.dumps({"message": {"content": " world"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.aiter_lines = MagicMock(return_value=_async_lines(lines))
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    config = LLMConfig(provider="ollama", model="llama3:8b")
    adapter = OllamaAdapter(config=config)
    adapter._client = AsyncMock()
    adapter._client.stream = MagicMock(return_value=mock_resp)

    chunks = []
    async for chunk in adapter.stream([{"role": "user", "content": "hi"}]):
        chunks.append(chunk)

    assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_stream_raises_llm_error_on_http_failure():
    from tavern.llm.ollama_llm import OllamaAdapter

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
    )
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    config = LLMConfig(provider="ollama", model="llama3:8b")
    adapter = OllamaAdapter(config=config)
    adapter._client = AsyncMock()
    adapter._client.stream = MagicMock(return_value=mock_resp)

    with pytest.raises(LLMError, match="Ollama stream failed"):
        async for _ in adapter.stream([{"role": "user", "content": "hi"}]):
            pass


def test_registry_registers_ollama():
    from tavern.llm.ollama_llm import OllamaAdapter
    config = LLMConfig(provider="ollama", model="llama3:8b")
    adapter = LLMRegistry.create(config)
    assert isinstance(adapter, OllamaAdapter)
