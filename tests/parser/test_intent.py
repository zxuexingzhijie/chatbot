from unittest.mock import AsyncMock

import pytest

from tavern.engine.actions import ActionType
from tavern.parser.intent import IntentParser
from tavern.world.models import ActionRequest


@pytest.fixture
def mock_llm_service():
    return AsyncMock()


@pytest.fixture
def parser(mock_llm_service):
    return IntentParser(llm_service=mock_llm_service)


class TestIntentParser:
    @pytest.mark.asyncio
    async def test_parse_move_intent(self, parser, mock_llm_service):
        mock_llm_service.classify_intent = AsyncMock(
            return_value=ActionRequest(
                action=ActionType.MOVE,
                target="bar_area",
                detail="走向吧台",
                confidence=0.95,
            )
        )
        result = await parser.parse(
            "我要去吧台",
            location_id="tavern_hall",
            npcs=["traveler"],
            items=["old_notice"],
            exits=["north", "east", "west"],
        )
        assert result.action == ActionType.MOVE
        assert result.target == "bar_area"

    @pytest.mark.asyncio
    async def test_parse_look_intent(self, parser, mock_llm_service):
        mock_llm_service.classify_intent = AsyncMock(
            return_value=ActionRequest(
                action=ActionType.LOOK,
                target=None,
                detail="环顾四周",
                confidence=0.9,
            )
        )
        result = await parser.parse(
            "看看周围",
            location_id="tavern_hall",
            npcs=["traveler"],
            items=["old_notice"],
            exits=["north", "east", "west"],
        )
        assert result.action == ActionType.LOOK

    @pytest.mark.asyncio
    async def test_low_confidence_falls_back_to_custom(self, parser, mock_llm_service):
        mock_llm_service.classify_intent = AsyncMock(
            return_value=ActionRequest(
                action=ActionType.MOVE,
                target="bar_area",
                detail="模糊",
                confidence=0.3,
            )
        )
        result = await parser.parse(
            "嗯...",
            location_id="tavern_hall",
            npcs=[],
            items=[],
            exits=[],
        )
        assert result.action == ActionType.CUSTOM

    @pytest.mark.asyncio
    async def test_llm_error_returns_custom(self, parser, mock_llm_service):
        mock_llm_service.classify_intent = AsyncMock(
            side_effect=Exception("LLM error")
        )
        result = await parser.parse(
            "随便说说",
            location_id="tavern_hall",
            npcs=[],
            items=[],
            exits=[],
        )
        assert result.action == ActionType.CUSTOM
