from unittest.mock import AsyncMock, MagicMock

import pytest

from tavern.engine.actions import ActionType
from tavern.llm.adapter import LLMConfig, LLMRegistry
from tavern.llm.openai_llm import OpenAIAdapter
from tavern.llm.service import LLMService
from tavern.world.models import ActionRequest


class TestLLMConfig:
    def test_create_config(self):
        config = LLMConfig(
            provider="openai", model="gpt-4o-mini", temperature=0.1, max_tokens=200
        )
        assert config.provider == "openai"
        assert config.model == "gpt-4o-mini"

    def test_default_values(self):
        config = LLMConfig(provider="openai", model="gpt-4o-mini")
        assert config.timeout == 30.0
        assert config.max_retries == 3


class TestLLMRegistry:
    def test_create_openai_adapter(self):
        config = LLMConfig(provider="openai", model="gpt-4o-mini")
        adapter = LLMRegistry.create(config)
        assert isinstance(adapter, OpenAIAdapter)

    def test_unknown_provider_raises(self):
        config = LLMConfig(provider="unknown", model="x")
        with pytest.raises(ValueError, match="unknown"):
            LLMRegistry.create(config)


class TestOpenAIAdapter:
    @pytest.mark.asyncio
    async def test_complete_returns_parsed_model(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"action": "move", "target": "bar_area",'
            ' "detail": "走向吧台", "confidence": 0.9}'
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        adapter = OpenAIAdapter(
            config=LLMConfig(provider="openai", model="gpt-4o-mini")
        )
        adapter._client = mock_client

        messages = [{"role": "user", "content": "我想去吧台"}]
        result = await adapter.complete(messages, response_format=ActionRequest)
        assert isinstance(result, ActionRequest)
        assert result.action == ActionType.MOVE

    @pytest.mark.asyncio
    async def test_complete_returns_string_without_format(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "你走向吧台。"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        adapter = OpenAIAdapter(
            config=LLMConfig(provider="openai", model="gpt-4o-mini")
        )
        adapter._client = mock_client

        messages = [{"role": "user", "content": "test"}]
        result = await adapter.complete(messages)
        assert result == "你走向吧台。"


class TestLLMService:
    @pytest.mark.asyncio
    async def test_classify_intent(self):
        mock_adapter = AsyncMock()
        mock_adapter.complete = AsyncMock(
            return_value=ActionRequest(
                action=ActionType.MOVE,
                target="bar_area",
                detail="走向吧台",
                confidence=0.95,
            )
        )
        service = LLMService(
            intent_adapter=mock_adapter, narrative_adapter=mock_adapter
        )
        scene_context = {
            "location": "tavern_hall",
            "npcs": ["traveler"],
            "items": ["old_notice"],
            "exits": ["north", "east", "west"],
        }
        result = await service.classify_intent("我想去吧台", scene_context)
        assert result.action == ActionType.MOVE
        assert result.target == "bar_area"
