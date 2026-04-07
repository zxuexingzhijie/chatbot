from pathlib import Path

import pytest

from tavern.world.loader import load_scenario
from tavern.world.models import CharacterRole
from tavern.world.state import WorldState

SCENARIO_PATH = Path(__file__).parent.parent.parent / "data" / "scenarios" / "tavern"


class TestLoadScenario:
    def test_returns_world_state(self):
        state = load_scenario(SCENARIO_PATH)
        assert isinstance(state, WorldState)

    def test_loads_all_locations(self):
        state = load_scenario(SCENARIO_PATH)
        assert len(state.locations) == 5
        assert "tavern_hall" in state.locations
        assert "bar_area" in state.locations
        assert "cellar" in state.locations

    def test_loads_player(self):
        state = load_scenario(SCENARIO_PATH)
        player = state.characters["player"]
        assert player.role == CharacterRole.PLAYER
        assert player.location_id == "tavern_hall"

    def test_loads_npcs(self):
        state = load_scenario(SCENARIO_PATH)
        assert "bartender_grim" in state.characters
        assert "traveler" in state.characters
        assert "mysterious_guest" in state.characters

    def test_loads_items(self):
        state = load_scenario(SCENARIO_PATH)
        assert "cellar_key" in state.items
        assert "old_notice" in state.items

    def test_locked_exit_loaded(self):
        state = load_scenario(SCENARIO_PATH)
        cellar_exit = state.locations["bar_area"].exits["down"]
        assert cellar_exit.locked
        assert cellar_exit.key_item == "cellar_key"

    def test_player_id_set(self):
        state = load_scenario(SCENARIO_PATH)
        assert state.player_id == "player"

    def test_initial_turn_is_zero(self):
        state = load_scenario(SCENARIO_PATH)
        assert state.turn == 0
