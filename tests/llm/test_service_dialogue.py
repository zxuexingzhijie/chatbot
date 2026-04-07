import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from tavern.dialogue.context import DialogueResponse, DialogueSummary
from tavern.llm.service import LLMService


@pytest.fixture
def mock_intent_adapter():
    return AsyncMock()


@pytest.fixture
def mock_narrative_adapter():
    return AsyncMock()


@pytest.fixture
def llm_service(mock_intent_adapter, mock_narrative_adapter):
    return LLMService(
        intent_adapter=mock_intent_adapter,
        narrative_adapter=mock_narrative_adapter,
    )


class TestGenerateDialogue:
    @pytest.mark.asyncio
    async def test_returns_dialogue_response(self, llm_service, mock_narrative_adapter):
        mock_narrative_adapter.complete = AsyncMock(
            return_value='{"text": "你好，冒险者。", "trust_delta": 1, "mood": "平静", "wants_to_end": false}'
        )
        result = await llm_service.generate_dialogue(
            system_prompt="你是NPC",
            messages=[{"role": "user", "content": "你好"}],
        )
        assert isinstance(result, DialogueResponse)
        assert result.text == "你好，冒险者。"
        assert result.trust_delta == 1
        assert result.mood == "平静"
        assert result.wants_to_end is False

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self, llm_service, mock_narrative_adapter):
        mock_narrative_adapter.complete = AsyncMock(return_value="不是JSON")
        result = await llm_service.generate_dialogue(
            system_prompt="你是NPC",
            messages=[{"role": "user", "content": "你好"}],
        )
        assert isinstance(result, DialogueResponse)
        assert result.trust_delta == 0
        assert result.wants_to_end is False

    @pytest.mark.asyncio
    async def test_clamps_trust_delta_positive(self, llm_service, mock_narrative_adapter):
        mock_narrative_adapter.complete = AsyncMock(
            return_value='{"text": "...", "trust_delta": 99, "mood": "x", "wants_to_end": false}'
        )
        result = await llm_service.generate_dialogue(
            system_prompt="你是NPC",
            messages=[],
        )
        assert result.trust_delta == 5

    @pytest.mark.asyncio
    async def test_clamps_trust_delta_negative(self, llm_service, mock_narrative_adapter):
        mock_narrative_adapter.complete = AsyncMock(
            return_value='{"text": "...", "trust_delta": -99, "mood": "x", "wants_to_end": false}'
        )
        result = await llm_service.generate_dialogue(
            system_prompt="你是NPC",
            messages=[],
        )
        assert result.trust_delta == -5


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_returns_summary_dict(self, llm_service, mock_intent_adapter):
        mock_intent_adapter.complete = AsyncMock(
            return_value='{"summary": "旅行者分享了北方的传说。", "key_info": ["北方有宝藏"]}'
        )
        result = await llm_service.generate_summary(
            summary_prompt="请总结",
        )
        assert result["summary"] == "旅行者分享了北方的传说。"
        assert "北方有宝藏" in result["key_info"]

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self, llm_service, mock_intent_adapter):
        mock_intent_adapter.complete = AsyncMock(return_value="不是JSON")
        result = await llm_service.generate_summary(
            summary_prompt="请总结",
        )
        assert "summary" in result
        assert "key_info" in result
