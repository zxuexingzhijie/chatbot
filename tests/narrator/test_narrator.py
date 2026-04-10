import pytest
from unittest.mock import AsyncMock, MagicMock

from tavern.engine.actions import ActionType
from tavern.narrator.narrator import Narrator
from tavern.narrator.prompts import build_ending_prompt
from tavern.world.models import ActionResult
from tavern.world.state import WorldState


async def _async_gen(*values):
    for v in values:
        yield v


async def _raise_on_iter():
    raise RuntimeError("LLM failed")
    yield  # make it an async generator


@pytest.fixture
def mock_llm_service():
    svc = MagicMock()
    svc.stream_narrative = MagicMock()
    return svc


@pytest.fixture
def narrator(mock_llm_service):
    return Narrator(llm_service=mock_llm_service)


@pytest.fixture
def sample_state(sample_world_state):
    return sample_world_state


class TestNarrator:
    @pytest.mark.asyncio
    async def test_yields_llm_chunks_on_success(self, narrator, mock_llm_service, sample_world_state):
        mock_llm_service.stream_narrative = MagicMock(
            return_value=_async_gen("你走进", "了大厅。")
        )
        result = ActionResult(
            success=True,
            action=ActionType.MOVE,
            message="你进入了酒馆大厅。",
            target="tavern_hall",
        )
        chunks = []
        async for chunk in narrator.stream_narrative(result, sample_world_state):
            chunks.append(chunk)
        assert chunks == ["你走进", "了大厅。"]

    @pytest.mark.asyncio
    async def test_fallback_on_llm_exception(self, narrator, mock_llm_service, sample_world_state):
        mock_llm_service.stream_narrative = MagicMock(
            return_value=_raise_on_iter()
        )
        result = ActionResult(
            success=True,
            action=ActionType.LOOK,
            message="你环顾四周，看到了酒馆大厅。",
        )
        chunks = []
        async for chunk in narrator.stream_narrative(result, sample_world_state):
            chunks.append(chunk)
        assert "".join(chunks) == "你环顾四周，看到了酒馆大厅。"

    @pytest.mark.asyncio
    async def test_builds_context_with_location_info(self, narrator, mock_llm_service, sample_world_state):
        captured_system: list[str] = []
        captured_message: list[str] = []

        async def capturing_stream(system_prompt, action_message):
            captured_system.append(system_prompt)
            captured_message.append(action_message)
            return
            yield

        mock_llm_service.stream_narrative = capturing_stream
        result = ActionResult(
            success=True,
            action=ActionType.LOOK,
            message="你仔细观察周围。",
        )
        async for _ in narrator.stream_narrative(result, sample_world_state):
            pass

        assert len(captured_system) == 1
        # Location name should appear in the prompt
        assert "酒馆大厅" in captured_system[0]
        # Action message is the user content
        assert captured_message[0] == "你仔细观察周围。"

    @pytest.mark.asyncio
    async def test_target_item_id_converted_to_name(self, narrator, mock_llm_service, sample_world_state):
        captured_messages: list[str] = []

        async def capturing_stream(system_prompt, action_message):
            captured_messages.append(action_message)
            return
            yield

        mock_llm_service.stream_narrative = capturing_stream
        result = ActionResult(
            success=True,
            action=ActionType.TAKE,
            message="你拾起了旧告示。",
            target="old_notice",
        )
        async for _ in narrator.stream_narrative(result, sample_world_state):
            pass

        full_text = " ".join(captured_messages)
        # "旧告示" (item name) should appear, not the raw ID "old_notice"
        assert "旧告示" in full_text

    @pytest.mark.asyncio
    async def test_target_npc_id_converted_to_name(self, narrator, mock_llm_service, sample_world_state):
        captured: list[str] = []

        async def capturing_stream(system_prompt, action_message):
            captured.append(system_prompt + action_message)
            return
            yield

        mock_llm_service.stream_narrative = capturing_stream
        result = ActionResult(
            success=True,
            action=ActionType.TALK,
            message="你向旅行者打了个招呼。",
            target="traveler",
        )
        async for _ in narrator.stream_narrative(result, sample_world_state):
            pass

        full_text = " ".join(captured)
        assert "旅行者" in full_text


class TestEndingPrompt:
    def test_build_ending_prompt_structure(self, sample_world_state):
        messages = build_ending_prompt(
            ending_id="good_ending",
            narrator_hint="温暖收束",
            state=sample_world_state,
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "结局" in messages[0]["content"]
        assert "good_ending" in messages[1]["content"]
        assert "温暖收束" in messages[1]["content"]

    def test_build_ending_prompt_includes_quests(self, sample_world_state):
        messages = build_ending_prompt(
            ending_id="good_ending",
            narrator_hint="hint",
            state=sample_world_state,
        )
        system_content = messages[0]["content"]
        assert "任务" in system_content or "quest" in system_content.lower()

    def test_build_ending_prompt_with_memory(self, sample_world_state):
        memory = MagicMock()
        memory.recent_events = "玩家揭开了密道的秘密"
        memory.relationship_summary = "酒保: 信任 30"
        messages = build_ending_prompt(
            ending_id="good_ending",
            narrator_hint="hint",
            state=sample_world_state,
            memory=memory,
        )
        system_content = messages[0]["content"]
        assert "密道" in system_content
        assert "酒保" in system_content


class TestEndingNarrative:
    @pytest.mark.asyncio
    async def test_stream_ending_yields_chunks(self, narrator, mock_llm_service, sample_world_state):
        mock_llm_service.stream_narrative = MagicMock(
            return_value=_async_gen("夜色温柔，", "冒险者踏上新的旅途。")
        )
        chunks = []
        async for chunk in narrator.stream_ending_narrative(
            ending_id="good_ending",
            narrator_hint="温暖收束",
            state=sample_world_state,
        ):
            chunks.append(chunk)
        assert chunks == ["夜色温柔，", "冒险者踏上新的旅途。"]

    @pytest.mark.asyncio
    async def test_stream_ending_fallback_on_error(self, narrator, mock_llm_service, sample_world_state):
        mock_llm_service.stream_narrative = MagicMock(
            return_value=_raise_on_iter()
        )
        chunks = []
        async for chunk in narrator.stream_ending_narrative(
            ending_id="good_ending",
            narrator_hint="温暖收束",
            state=sample_world_state,
        ):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert "good_ending" in chunks[0]


class TestContinueNarrative:
    @pytest.mark.asyncio
    async def test_stream_continue_yields_chunks(self, narrator, mock_llm_service, sample_world_state):
        mock_llm_service.stream_narrative = MagicMock(
            return_value=_async_gen("时间流逝，", "酒馆中灯火摇曳。")
        )
        chunks = []
        async for chunk in narrator.stream_continue_narrative(sample_world_state):
            chunks.append(chunk)
        assert chunks == ["时间流逝，", "酒馆中灯火摇曳。"]

    @pytest.mark.asyncio
    async def test_stream_continue_fallback_on_error(self, narrator, mock_llm_service, sample_world_state):
        mock_llm_service.stream_narrative = MagicMock(
            return_value=_raise_on_iter()
        )
        chunks = []
        async for chunk in narrator.stream_continue_narrative(sample_world_state):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert "酒馆" in chunks[0]
