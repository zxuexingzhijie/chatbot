from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from pathlib import Path

from tavern.world.models import Character, CharacterRole, Location
from tavern.world.state import WorldState, StateManager
from tavern.world.persistence import SaveManager


@pytest.fixture
def mock_state():
    return WorldState(
        turn=1,
        player_id="player",
        locations={
            "room": Location(id="room", name="房间", description="一个房间")
        },
        characters={
            "player": Character(
                id="player", name="冒险者",
                role=CharacterRole.PLAYER,
                stats={"hp": 100},
                location_id="room",
            )
        },
        items={},
    )


@pytest.fixture
def app(mock_state, tmp_path):
    from tavern.cli.app import GameApp
    game = GameApp.__new__(GameApp)
    game._state_manager = StateManager(initial_state=mock_state)
    game._renderer = MagicMock()
    game._memory = MagicMock()
    game._memory.sync_to_state.return_value = mock_state
    game._dialogue_manager = MagicMock()
    game._dialogue_manager.is_active = False
    game._dialogue_ctx = None
    game._scenario_path = Path("data/scenarios/tavern")
    game._game_config = {"saves_dir": str(tmp_path / "saves"), "undo_history_size": 50}
    game._save_manager = SaveManager(tmp_path / "saves")
    return game


def test_save_command_calls_save_manager(app, tmp_path):
    app._handle_system_command("save", "autosave")
    assert (tmp_path / "saves" / "autosave.json").exists()
    app._renderer.render_save_success.assert_called_once()


def test_save_command_named_slot(app, tmp_path):
    app._handle_system_command("save", "mygame")
    assert (tmp_path / "saves" / "mygame.json").exists()
