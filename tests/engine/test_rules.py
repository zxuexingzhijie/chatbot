import pytest

from tavern.engine.actions import ActionType
from tavern.engine.rules import RulesEngine
from tavern.world.models import ActionRequest, Item, Location, Exit
from tavern.world.state import StateDiff, WorldState


@pytest.fixture
def rules_engine():
    return RulesEngine()


class TestMoveAction:
    def test_move_to_valid_exit(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert diff is not None
        assert diff.updated_characters["player"]["location_id"] == "bar_area"

    def test_move_to_invalid_direction(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.MOVE, target="up")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert not result.success
        assert diff is None

    def test_move_to_locked_exit(self, rules_engine, sample_world_state):
        state = sample_world_state.apply(
            StateDiff(updated_characters={"player": {"location_id": "bar_area"}})
        )
        request = ActionRequest(action=ActionType.MOVE, target="down")
        result, diff = rules_engine.validate(request, state)
        assert not result.success
        assert diff is None

    def test_move_to_locked_exit_with_key(self, rules_engine, sample_world_state):
        state = sample_world_state.apply(
            StateDiff(
                updated_characters={
                    "player": {
                        "location_id": "bar_area",
                        "inventory": ("cellar_key",),
                    }
                }
            )
        )
        request = ActionRequest(action=ActionType.MOVE, target="down")
        result, diff = rules_engine.validate(request, state)
        assert result.success


class TestLookAction:
    def test_look_at_current_location(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.LOOK)
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert "酒馆大厅" in result.message
        assert diff is None

    def test_look_at_specific_item(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.LOOK, target="old_notice")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert "告示" in result.message

    def test_look_at_nonexistent_item(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.LOOK, target="magic_sword")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert not result.success


class TestTakeAction:
    def test_take_portable_item(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.TAKE, target="old_notice")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert diff is not None
        assert "old_notice" in diff.updated_characters["player"]["inventory"]
        assert "old_notice" not in diff.updated_locations["tavern_hall"]["items"]

    def test_take_nonexistent_item(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.TAKE, target="ghost_gem")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert not result.success
        assert diff is None

    def test_take_non_portable_item(self, rules_engine, sample_world_state):
        heavy_item = Item(
            id="heavy_rock",
            name="巨石",
            description="太重了搬不动",
            portable=False,
        )
        test_loc = Location(
            id="test_room",
            name="测试房间",
            description="测试",
            exits={},
            items=("heavy_rock",),
            npcs=(),
        )
        state = WorldState(
            turn=0,
            player_id="player",
            locations={**sample_world_state.locations, "test_room": test_loc},
            characters={
                **sample_world_state.characters,
                "player": sample_world_state.characters["player"].model_copy(
                    update={"location_id": "test_room"}
                ),
            },
            items={**sample_world_state.items, "heavy_rock": heavy_item},
        )
        request = ActionRequest(action=ActionType.TAKE, target="heavy_rock")
        result, diff = rules_engine.validate(request, state)
        assert not result.success
        assert diff is None


class TestCustomAction:
    def test_custom_action_always_succeeds(self, rules_engine, sample_world_state):
        request = ActionRequest(
            action=ActionType.CUSTOM, detail="跳一段舞", confidence=0.3
        )
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert diff is None


class TestTalkAction:
    def test_talk_npc_in_location(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.TALK, target="traveler")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert result.target == "traveler"
        assert diff is None

    def test_talk_npc_not_in_location(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.TALK, target="bartender_grim")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert not result.success
        assert diff is None

    def test_talk_nonexistent_target(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.TALK, target="ghost")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert not result.success
        assert diff is None

    def test_persuade_npc_in_location(self, rules_engine, sample_world_state):
        request = ActionRequest(action=ActionType.PERSUADE, target="traveler")
        result, diff = rules_engine.validate(request, sample_world_state)
        assert result.success
        assert result.target == "traveler"
        assert diff is None
