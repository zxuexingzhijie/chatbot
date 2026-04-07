import pytest
from unittest.mock import AsyncMock, MagicMock

from tavern.dialogue.context import DialogueContext, DialogueResponse, DialogueSummary
from tavern.world.models import Character, CharacterRole, Location, Event
from tavern.world.state import WorldState, StateManager


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
        from tavern.cli.app import GameApp
        state_manager = StateManager(initial_state=mock_state)
        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._renderer = MagicMock()

        app._apply_dialogue_end(mock_summary)

        new_trust = state_manager.current.characters["traveler"].stats["trust"]
        assert new_trust == 13  # 10 + 3

    def test_apply_dialogue_end_writes_summary_event(self, mock_state, mock_summary):
        from tavern.cli.app import GameApp
        state_manager = StateManager(initial_state=mock_state)
        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._renderer = MagicMock()

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
        from tavern.cli.app import GameApp
        state_manager = StateManager(initial_state=mock_state)
        mock_dialogue_manager = MagicMock()
        mock_dialogue_manager.end = AsyncMock(return_value=mock_summary)

        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._dialogue_manager = mock_dialogue_manager
        app._renderer = MagicMock()
        app._dialogue_ctx = mock_dialogue_ctx

        await app._process_dialogue_input("bye", mock_dialogue_ctx)

        mock_dialogue_manager.end.assert_called_once_with(mock_dialogue_ctx)

    @pytest.mark.asyncio
    async def test_process_dialogue_input_normal_calls_respond(
        self, mock_state, mock_dialogue_ctx, mock_dialogue_response
    ):
        from tavern.cli.app import GameApp
        state_manager = StateManager(initial_state=mock_state)
        mock_dialogue_manager = MagicMock()
        mock_dialogue_manager.respond = AsyncMock(
            return_value=(mock_dialogue_ctx, mock_dialogue_response)
        )

        app = GameApp.__new__(GameApp)
        app._state_manager = state_manager
        app._dialogue_manager = mock_dialogue_manager
        app._renderer = MagicMock()
        app._dialogue_ctx = mock_dialogue_ctx

        await app._process_dialogue_input("你好", mock_dialogue_ctx)

        mock_dialogue_manager.respond.assert_called_once_with(
            mock_dialogue_ctx, "你好", mock_state
        )
