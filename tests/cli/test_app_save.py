from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from pathlib import Path

from tavern.world.models import Character, CharacterRole, Location
from tavern.world.state import WorldState, StateManager, StateDiff
from tavern.world.persistence import SaveManager
from tavern.engine.actions import ActionType
from tavern.world.models import ActionResult


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
    from tavern.data import get_bundled_scenario
    game._scenario_path = get_bundled_scenario("tavern")
    game._game_config = {"saves_dir": str(tmp_path / "saves"), "undo_history_size": 50}
    game._save_manager = SaveManager(tmp_path / "saves")
    return game


def test_autosave_after_successful_action(app, tmp_path, mock_state):
    diff = StateDiff(turn_increment=1)
    result = ActionResult(success=True, action=ActionType.MOVE, message="移动了")
    app._state_manager.commit(diff, result)
    new_state = app._memory.sync_to_state(app.state)
    app._save_manager.save(new_state, "autosave")
    assert (tmp_path / "saves" / "autosave.json").exists()


def test_autosave_after_dialogue_end(app, tmp_path, mock_state):
    app._memory.sync_to_state.return_value = mock_state
    new_state = app._memory.sync_to_state(app.state)
    app._save_manager.save(new_state, "autosave")
    assert (tmp_path / "saves" / "autosave.json").exists()
