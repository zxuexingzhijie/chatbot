import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from pathlib import Path

from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary
from tavern.world.models import Character, CharacterRole, Location
from tavern.world.state import WorldState, StateManager, StateDiff
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
def mock_summary():
    return DialogueSummary(
        npc_id="traveler",
        summary_text="进行了友好交谈。",
        total_trust_delta=3,
        key_info=("旅行者来自北方",),
        turns_count=2,
    )


class TestGameAppMemory:
    def test_memory_initialized_in_init(self, mock_state):
        """GameApp.__init__ creates a MemorySystem with initial_state."""
        fake_config = {
            "llm": {
                "intent": {"provider": "openai", "model": "gpt-4o-mini"},
                "narrative": {"provider": "openai", "model": "gpt-4o"},
            },
            "game": {"scenario": "tavern"},
        }
        with patch("tavern.cli.app.load_scenario", return_value=mock_state), \
             patch("tavern.cli.app.validate_scenario", return_value=[]), \
             patch("tavern.cli.app.load_scenario_meta", return_value=MagicMock(name="Test")), \
             patch("tavern.cli.app.LLMRegistry") as mock_registry, \
             patch.object(GameApp, "_load_config", return_value=fake_config), \
             patch("pathlib.Path.exists", return_value=False), \
             patch("tavern.cli.app.MemorySystem") as mock_memory_cls:
            mock_registry.create.return_value = MagicMock()
            mock_memory_cls.return_value = MagicMock()

            app = GameApp.__new__(GameApp)
            GameApp.__init__(app, config_path="nonexistent.yaml")

            mock_memory_cls.assert_called_once()
            call_kwargs = mock_memory_cls.call_args
            assert call_kwargs.kwargs.get("state") == mock_state or call_kwargs.args[0] == mock_state

    @pytest.mark.asyncio
    async def test_handle_free_input_calls_apply_diff_after_commit(self, mock_state):
        """After commit in _handle_free_input, memory.apply_diff is called."""
        from tavern.world.models import ActionRequest, ActionResult
        from tavern.engine.actions import ActionType
        from tavern.world.state import StateDiff

        state_manager = StateManager(initial_state=mock_state)
        mock_memory = MagicMock()
        mock_memory.build_context.return_value = MagicMock()

        mock_dialogue_manager = MagicMock()
        mock_dialogue_manager.is_active = False

        mock_narrator = MagicMock()
        mock_narrator.stream_narrative.return_value = _async_gen(["text"])

        fake_result = ActionResult(success=True, action=ActionType.LOOK, message="看见大厅")
        fake_diff = StateDiff(turn_increment=1)

        mock_rules = MagicMock()
        mock_rules.validate.return_value = (fake_result, fake_diff)

        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._memory = mock_memory
        app._dialogue_manager = mock_dialogue_manager
        app._dialogue_ctx = None
        app._narrator = mock_narrator
        app._show_intent = False
        app._rules = mock_rules
        app._renderer = MagicMock()
        app._renderer.render_stream = AsyncMock()
        app._parser = MagicMock()
        app._parser.parse = AsyncMock(
            return_value=ActionRequest(action=ActionType.LOOK)
        )
        app._save_manager = MagicMock()
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

        await app._handle_free_input("看看四周")

        mock_memory.apply_diff.assert_called_once_with(fake_diff, state_manager.current)

    @pytest.mark.asyncio
    async def test_process_dialogue_input_builds_memory_ctx_each_round(
        self, mock_state, mock_dialogue_ctx
    ):
        """_process_dialogue_input calls memory.build_context with ctx.npc_id."""
        mock_response = DialogueResponse(
            text="你好！", trust_delta=1, mood="平静", wants_to_end=False
        )

        state_manager = StateManager(initial_state=mock_state)
        mock_memory = MagicMock()
        mock_memory_ctx = MagicMock()
        mock_memory.build_context.return_value = mock_memory_ctx

        mock_dialogue_manager = MagicMock()
        mock_dialogue_manager.respond = AsyncMock(
            return_value=(mock_dialogue_ctx, mock_response)
        )

        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._memory = mock_memory
        app._dialogue_manager = mock_dialogue_manager
        app._dialogue_ctx = mock_dialogue_ctx
        app._renderer = MagicMock()
        app._renderer.render_dialogue_with_typewriter = AsyncMock()
        app._last_narrative = ""

        await app._process_dialogue_input("你好", mock_dialogue_ctx)

        mock_memory.build_context.assert_called_once_with(
            actor="traveler",
            state=mock_state,
        )
        mock_dialogue_manager.respond.assert_called_once_with(
            mock_dialogue_ctx, "你好", mock_state, mock_memory_ctx,
            scene_context="",
        )

    def test_apply_dialogue_end_adds_relationship_changes(self, mock_state, mock_summary):
        """_apply_dialogue_end includes relationship_changes in trust_diff."""
        state_manager = StateManager(initial_state=mock_state)
        mock_memory = MagicMock()

        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._memory = mock_memory
        app._renderer = MagicMock()
        app._save_manager = MagicMock()

        committed_diffs = []
        original_commit = state_manager.commit

        def capture_commit(diff, action):
            committed_diffs.append(diff)
            return original_commit(diff, action)

        state_manager.commit = capture_commit

        app._apply_dialogue_end(mock_summary)

        assert len(committed_diffs) >= 1
        trust_diff = committed_diffs[0]
        assert len(trust_diff.relationship_changes) == 1
        rel_change = trust_diff.relationship_changes[0]
        assert rel_change["src"] == "player"
        assert rel_change["tgt"] == "traveler"
        assert rel_change["delta"] == 3


async def _async_gen(items):
    for item in items:
        yield item
