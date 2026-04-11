import pytest
from unittest.mock import MagicMock, patch

from tavern.world.models import Character, CharacterRole, Location
from tavern.world.state import WorldState
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
