import pytest
from unittest.mock import AsyncMock, MagicMock

from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary
from tavern.world.models import Character, CharacterRole, Location, Event
from tavern.world.state import WorldState, StateManager
from tavern.cli.app import GameApp


@pytest.fixture
def mock_state():
    return WorldState(
        turn=5,
        player_id="player",
        locations={
            "tavern_hall": Location(
                id="tavern_hall",
                name="酒馆大厅",
                description="大厅",
                npcs=("traveler",),
            )
        },
        characters={
            "player": Character(
                id="player", name="冒险者",
                role=CharacterRole.PLAYER,
                stats={"hp": 100},
                location_id="tavern_hall",
            ),
            "traveler": Character(
                id="traveler", name="旅行者",
                role=CharacterRole.NPC,
                traits=("友善",),
                stats={"trust": 10},
                location_id="tavern_hall",
            ),
        },
        items={},
    )


@pytest.fixture
def mock_dialogue_ctx():
    return DialogueContext(
        npc_id="traveler",
        npc_name="旅行者",
        npc_traits=("友善",),
        trust=10,
        tone="neutral",
        messages=(),
        location_id="tavern_hall",
        turn_entered=5,
    )


@pytest.fixture
def mock_dialogue_response():
    return DialogueResponse(text="你好！", trust_delta=1, mood="平静", wants_to_end=False)


@pytest.fixture
def mock_summary():
    return DialogueSummary(
        npc_id="traveler",
        summary_text="进行了友好交谈。",
        total_trust_delta=3,
        key_info=("旅行者来自北方",),
        turns_count=2,
    )


class TestGameAppDialogueFlow:
    def test_apply_dialogue_end_updates_trust(self, mock_state, mock_summary):
        state_manager = StateManager(initial_state=mock_state)
        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._renderer = MagicMock()
        app._memory = MagicMock()
        app._save_manager = MagicMock()

        app._apply_dialogue_end(mock_summary)

        new_trust = state_manager.current.characters["traveler"].stats["trust"]
        assert new_trust == 13  # 10 + 3

    def test_apply_dialogue_end_writes_summary_event(self, mock_state, mock_summary):
        state_manager = StateManager(initial_state=mock_state)
        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._renderer = MagicMock()
        app._memory = MagicMock()
        app._save_manager = MagicMock()

        app._apply_dialogue_end(mock_summary)

        new_state = state_manager.current
        dialogue_events = [
            e for e in new_state.timeline if e.type == "dialogue_summary"
        ]
        assert len(dialogue_events) == 1
        assert dialogue_events[0].actor == "traveler"
        assert "进行了友好交谈" in dialogue_events[0].description

    @pytest.mark.asyncio
    async def test_process_dialogue_input_bye_ends_dialogue(
        self, mock_state, mock_dialogue_ctx, mock_summary
    ):
        state_manager = StateManager(initial_state=mock_state)
        mock_dialogue_manager = MagicMock()
        mock_dialogue_manager.end = AsyncMock(return_value=mock_summary)

        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._dialogue_manager = mock_dialogue_manager
        app._renderer = MagicMock()
        app._dialogue_ctx = mock_dialogue_ctx
        app._memory = MagicMock()
        app._save_manager = MagicMock()

        await app._process_dialogue_input("bye", mock_dialogue_ctx)

        mock_dialogue_manager.end.assert_called_once_with(mock_dialogue_ctx)

    @pytest.mark.asyncio
    async def test_process_dialogue_input_normal_calls_respond(
        self, mock_state, mock_dialogue_ctx, mock_dialogue_response
    ):
        state_manager = StateManager(initial_state=mock_state)
        mock_dialogue_manager = MagicMock()
        mock_dialogue_manager.respond = AsyncMock(
            return_value=(mock_dialogue_ctx, mock_dialogue_response)
        )

        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._dialogue_manager = mock_dialogue_manager
        app._renderer = MagicMock()
        app._renderer.render_dialogue_with_typewriter = AsyncMock()
        app._dialogue_ctx = mock_dialogue_ctx
        mock_memory = MagicMock()
        mock_memory_ctx = MagicMock()
        mock_memory.build_context.return_value = mock_memory_ctx
        app._memory = mock_memory
        app._last_narrative = ""

        await app._process_dialogue_input("你好", mock_dialogue_ctx)

        mock_dialogue_manager.respond.assert_called_once_with(
            mock_dialogue_ctx, "你好", mock_state, mock_memory_ctx,
            scene_context="",
        )


class TestNarrativeIntegration:
    @pytest.mark.asyncio
    async def test_successful_action_uses_render_stream_not_render_result(
        self, mock_state
    ):
        """render_stream called (not render_result) on successful non-dialogue action."""
        from unittest.mock import patch, AsyncMock, MagicMock
        from tavern.world.state import StateManager
        from tavern.dialogue.manager import DialogueManager
        from tavern.narrator.narrator import Narrator
        from tavern.cli.renderer import Renderer

        async def fake_stream(system_prompt, action_message):
            yield "叙事内容"

        mock_llm_service = MagicMock()
        mock_llm_service.stream_narrative = fake_stream

        state_manager = StateManager(initial_state=mock_state)
        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._renderer = MagicMock()
        app._renderer.render_status_bar = MagicMock()
        app._dialogue_manager = DialogueManager(llm_service=mock_llm_service)
        app._dialogue_ctx = None
        app._narrator = Narrator(llm_service=mock_llm_service)
        app._show_intent = False
        mock_memory = MagicMock()
        mock_memory.build_context.return_value = MagicMock()
        app._memory = mock_memory
        mock_story_engine = MagicMock()
        mock_story_engine.check = MagicMock(return_value=[])
        mock_story_engine.check_fail_forward = MagicMock(return_value=[])
        mock_story_engine.get_active_nodes = MagicMock(return_value=set())
        app._story_engine = mock_story_engine
        app._pending_story_hints = []
        app._ending_triggered = None
        app._game_over = False

        render_result_calls = []
        render_stream_calls = []
        app._renderer.render_result = lambda r: render_result_calls.append(r)

        async def mock_render_stream(stream, *, atmosphere="neutral"):
            async for _ in stream:
                pass
            render_stream_calls.append(True)

        app._renderer.render_stream = mock_render_stream

        from tavern.engine.rules import RulesEngine
        from tavern.parser.intent import IntentParser
        app._rules = RulesEngine()

        mock_intent = AsyncMock()
        from tavern.world.models import ActionRequest
        from tavern.engine.actions import ActionType
        mock_intent.complete = AsyncMock(
            return_value=ActionRequest(action=ActionType.LOOK)
        )
        app._parser = IntentParser(llm_service=MagicMock())
        app._last_narrative = ""
        mock_llm_service = MagicMock()
        mock_llm_service.generate_action_hints = AsyncMock(return_value=[])
        app._llm_service = mock_llm_service

        with patch.object(app._parser, "parse", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = ActionRequest(action=ActionType.LOOK)
            await app._handle_free_input("看看四周")

        assert len(render_stream_calls) == 1
        assert len(render_result_calls) == 0

    @pytest.mark.asyncio
    async def test_failed_action_uses_render_result_not_render_stream(
        self, mock_state
    ):
        """render_result called (not render_stream) on failed action."""
        from unittest.mock import patch, AsyncMock, MagicMock
        from tavern.world.state import StateManager
        from tavern.dialogue.manager import DialogueManager
        from tavern.narrator.narrator import Narrator
        from tavern.engine.rules import RulesEngine
        from tavern.parser.intent import IntentParser

        mock_llm_service = MagicMock()
        state_manager = StateManager(initial_state=mock_state)
        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._renderer = MagicMock()
        app._renderer.render_status_bar = MagicMock()
        app._dialogue_manager = DialogueManager(llm_service=mock_llm_service)
        app._dialogue_ctx = None
        app._narrator = Narrator(llm_service=mock_llm_service)
        app._show_intent = False
        app._rules = RulesEngine()
        app._parser = IntentParser(llm_service=MagicMock())
        mock_memory = MagicMock()
        mock_memory.build_context.return_value = MagicMock()
        app._memory = mock_memory
        mock_story_engine = MagicMock()
        mock_story_engine.check = MagicMock(return_value=[])
        mock_story_engine.check_fail_forward = MagicMock(return_value=[])
        mock_story_engine.get_active_nodes = MagicMock(return_value=set())
        app._story_engine = mock_story_engine
        app._pending_story_hints = []
        app._ending_triggered = None
        app._game_over = False
        app._last_narrative = ""
        mock_llm_svc = MagicMock()
        mock_llm_svc.generate_action_hints = AsyncMock(return_value=[])
        app._llm_service = mock_llm_svc

        render_result_calls = []
        render_stream_calls = []
        app._renderer.render_result = lambda r: render_result_calls.append(r)

        async def mock_render_stream(stream):
            render_stream_calls.append(True)

        app._renderer.render_stream = mock_render_stream

        with patch.object(app._parser, "parse", new_callable=AsyncMock) as mock_parse:
            from tavern.world.models import ActionRequest
            from tavern.engine.actions import ActionType
            mock_parse.return_value = ActionRequest(
                action=ActionType.MOVE, target="nowhere"
            )
            await app._handle_free_input("走向虚空")

        assert len(render_result_calls) == 1
        assert len(render_stream_calls) == 0
