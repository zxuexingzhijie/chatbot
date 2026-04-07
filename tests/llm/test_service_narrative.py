import pytest
from unittest.mock import AsyncMock, MagicMock

from tavern.llm.service import LLMService


async def _async_gen(*values):
    for v in values:
        yield v


@pytest.fixture
def mock_intent_adapter():
    return AsyncMock()


@pytest.fixture
def mock_narrative_adapter():
    adapter = MagicMock()
    adapter.stream = MagicMock()
    return adapter


@pytest.fixture
def llm_service(mock_intent_adapter, mock_narrative_adapter):
    return LLMService(
        intent_adapter=mock_intent_adapter,
        narrative_adapter=mock_narrative_adapter,
    )


class TestStreamNarrative:
    @pytest.mark.asyncio
    async def test_yields_chunks_from_narrative_adapter(
        self, llm_service, mock_narrative_adapter
    ):
        mock_narrative_adapter.stream = MagicMock(
            return_value=_async_gen("你走进了", "温暖的酒馆。")
        )
        chunks = []
        async for chunk in llm_service.stream_narrative(
            system_prompt="你是叙述者",
            action_message="你走进了酒馆大厅。",
        ):
            chunks.append(chunk)
        assert chunks == ["你走进了", "温暖的酒馆。"]

    @pytest.mark.asyncio
    async def test_passes_correct_messages_to_adapter(
        self, llm_service, mock_narrative_adapter
    ):
        captured: list[list[dict]] = []

        async def capturing_stream(messages):
            captured.append(messages)
            return
            yield  # make it an async generator

        mock_narrative_adapter.stream = capturing_stream
        async for _ in llm_service.stream_narrative(
            system_prompt="系统提示",
            action_message="行动消息",
        ):
            pass

        assert len(captured) == 1
        msgs = captured[0]
        assert msgs[0] == {"role": "system", "content": "系统提示"}
        assert msgs[1] == {"role": "user", "content": "行动消息"}
