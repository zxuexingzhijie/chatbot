import pytest

from tavern.engine.actions import ActionType
from tavern.world.models import ActionResult, Event
from tavern.world.state import StateDiff, StateManager, WorldState


class TestWorldState:
    def test_is_frozen(self, sample_world_state):
        with pytest.raises(Exception):
            sample_world_state.turn = 99

    def test_apply_diff_increments_turn(self, sample_world_state):
        diff = StateDiff(turn_increment=1)
        new_state = sample_world_state.apply(diff)
        assert new_state.turn == 1
        assert sample_world_state.turn == 0

    def test_apply_diff_updates_character(self, sample_world_state):
        diff = StateDiff(
            updated_characters={"player": {"location_id": "bar_area"}}
        )
        new_state = sample_world_state.apply(diff)
        assert new_state.characters["player"].location_id == "bar_area"
        assert sample_world_state.characters["player"].location_id == "tavern_hall"

    def test_apply_diff_removes_item_from_location(self, sample_world_state):
        diff = StateDiff(updated_locations={"tavern_hall": {"items": ()}})
        new_state = sample_world_state.apply(diff)
        assert "old_notice" not in new_state.locations["tavern_hall"].items

    def test_apply_diff_adds_item_to_inventory(self, sample_world_state):
        diff = StateDiff(
            updated_characters={"player": {"inventory": ("old_notice",)}}
        )
        new_state = sample_world_state.apply(diff)
        assert "old_notice" in new_state.characters["player"].inventory

    def test_apply_diff_adds_event(self, sample_world_state):
        event = Event(
            id="evt_1",
            turn=1,
            type="move",
            actor="player",
            description="玩家移动到吧台区",
        )
        diff = StateDiff(new_events=(event,))
        new_state = sample_world_state.apply(diff)
        assert len(new_state.timeline) == 1
        assert new_state.timeline[0].id == "evt_1"

    def test_apply_character_stat_deltas(self, sample_world_state):
        diff = StateDiff(
            character_stat_deltas={"bartender_grim": {"trust": 20}},
            turn_increment=0,
        )
        new_state = sample_world_state.apply(diff)
        assert new_state.characters["bartender_grim"].stats["trust"] == 20

    def test_apply_character_stat_deltas_additive(self, sample_world_state):
        diff1 = StateDiff(
            character_stat_deltas={"bartender_grim": {"trust": 15}},
            turn_increment=0,
        )
        state2 = sample_world_state.apply(diff1)
        diff2 = StateDiff(
            character_stat_deltas={"bartender_grim": {"trust": 10}},
            turn_increment=0,
        )
        state3 = state2.apply(diff2)
        assert state3.characters["bartender_grim"].stats["trust"] == 25

    def test_apply_character_stat_deltas_new_stat(self, sample_world_state):
        diff = StateDiff(
            character_stat_deltas={"bartender_grim": {"fear": 5}},
            turn_increment=0,
        )
        new_state = sample_world_state.apply(diff)
        assert new_state.characters["bartender_grim"].stats["fear"] == 5

    def test_apply_character_stat_deltas_unknown_character_ignored(self, sample_world_state):
        diff = StateDiff(
            character_stat_deltas={"nonexistent": {"trust": 10}},
            turn_increment=0,
        )
        new_state = sample_world_state.apply(diff)
        assert "nonexistent" not in new_state.characters


class TestStateManager:
    def test_current_returns_initial(self, sample_state_manager, sample_world_state):
        assert sample_state_manager.current.turn == sample_world_state.turn

    def test_commit_advances_state(self, sample_state_manager):
        diff = StateDiff(turn_increment=1)
        action = ActionResult(
            success=True, action=ActionType.LOOK, message="你环顾四周。"
        )
        new_state = sample_state_manager.commit(diff, action)
        assert new_state.turn == 1
        assert sample_state_manager.current.turn == 1

    def test_commit_stores_last_action(self, sample_state_manager):
        diff = StateDiff(turn_increment=1)
        action = ActionResult(
            success=True, action=ActionType.LOOK, message="你环顾四周。"
        )
        sample_state_manager.commit(diff, action)
        assert sample_state_manager.current.last_action == action

    def test_undo_restores_previous(self, sample_state_manager):
        diff = StateDiff(turn_increment=1)
        action = ActionResult(
            success=True, action=ActionType.LOOK, message="看"
        )
        sample_state_manager.commit(diff, action)
        assert sample_state_manager.current.turn == 1
        restored = sample_state_manager.undo()
        assert restored.turn == 0

    def test_undo_on_empty_history_returns_none(self, sample_state_manager):
        assert sample_state_manager.undo() is None

    def test_redo_after_undo(self, sample_state_manager):
        diff = StateDiff(turn_increment=1)
        action = ActionResult(
            success=True, action=ActionType.LOOK, message="看"
        )
        sample_state_manager.commit(diff, action)
        sample_state_manager.undo()
        redone = sample_state_manager.redo()
        assert redone.turn == 1

    def test_redo_on_empty_returns_none(self, sample_state_manager):
        assert sample_state_manager.redo() is None

    def test_commit_clears_redo_stack(self, sample_state_manager):
        diff1 = StateDiff(turn_increment=1)
        action1 = ActionResult(
            success=True, action=ActionType.LOOK, message="看"
        )
        sample_state_manager.commit(diff1, action1)
        sample_state_manager.undo()
        diff2 = StateDiff(turn_increment=1)
        action2 = ActionResult(
            success=True, action=ActionType.MOVE, message="走"
        )
        sample_state_manager.commit(diff2, action2)
        assert sample_state_manager.redo() is None


# --- story_active_since tests ---

def test_state_diff_has_story_active_since_updates():
    from tavern.world.state import StateDiff
    diff = StateDiff(story_active_since_updates={"node1": 5})
    assert diff.story_active_since_updates == {"node1": 5}


def test_world_state_apply_merges_story_active_since():
    from tavern.world.state import StateDiff, WorldState
    from tavern.world.models import Character, CharacterRole, Location, ActionResult
    from tavern.engine.actions import ActionType
    state = WorldState(
        turn=3,
        player_id="player",
        locations={"room": Location(id="room", name="R", description="d")},
        characters={"player": Character(id="player", name="P", role=CharacterRole.PLAYER, location_id="room")},
        story_active_since={"node_a": 1},
    )
    diff = StateDiff(story_active_since_updates={"node_b": 3}, turn_increment=0)
    result = ActionResult(success=True, action=ActionType.LOOK, message="ok")
    new_state = state.apply(diff, action=result)
    assert new_state.story_active_since == {"node_a": 1, "node_b": 3}


def test_world_state_apply_story_active_since_overwrite():
    from tavern.world.state import StateDiff, WorldState
    from tavern.world.models import Character, CharacterRole, Location, ActionResult
    from tavern.engine.actions import ActionType
    state = WorldState(
        turn=10,
        player_id="player",
        locations={"room": Location(id="room", name="R", description="d")},
        characters={"player": Character(id="player", name="P", role=CharacterRole.PLAYER, location_id="room")},
        story_active_since={"node_a": 1},
    )
    diff = StateDiff(story_active_since_updates={"node_a": 10}, turn_increment=0)
    result = ActionResult(success=True, action=ActionType.LOOK, message="ok")
    new_state = state.apply(diff, action=result)
    assert new_state.story_active_since["node_a"] == 10


class TestEndingsReached:
    def test_apply_new_endings_from_empty(self, sample_world_state):
        diff = StateDiff(new_endings=("good_ending",), turn_increment=0)
        new_state = sample_world_state.apply(diff)
        assert new_state.endings_reached == ("good_ending",)
        assert sample_world_state.endings_reached == ()

    def test_apply_new_endings_appends(self, sample_world_state):
        diff1 = StateDiff(new_endings=("neutral_ending",), turn_increment=0)
        state1 = sample_world_state.apply(diff1)
        diff2 = StateDiff(new_endings=("good_ending",), turn_increment=0)
        state2 = state1.apply(diff2)
        assert state2.endings_reached == ("neutral_ending", "good_ending")

    def test_apply_no_new_endings_unchanged(self, sample_world_state):
        diff = StateDiff(turn_increment=1)
        new_state = sample_world_state.apply(diff)
        assert new_state.endings_reached == ()


class TestApplyDoesNotMutateRelationships:
    def test_apply_does_not_mutate_relationships_snapshot(self, sample_world_state):
        diff = StateDiff(
            relationship_changes=(
                {"src": "player", "tgt": "bartender_grim", "delta": 10},
            ),
            turn_increment=1,
        )
        new_state = sample_world_state.apply(diff)
        assert new_state.relationships_snapshot == sample_world_state.relationships_snapshot


class TestUpdateSnapshot:
    def test_update_snapshot_replaces_state_preserving_history(self, sample_world_state):
        mgr = StateManager(initial_state=sample_world_state)
        diff = StateDiff(turn_increment=1)
        action = ActionResult(
            success=True, action=ActionType.LOOK, message="看"
        )
        mgr.commit(diff, action)
        assert mgr.current.turn == 1

        replacement = mgr.current.model_copy(
            update={"relationships_snapshot": {"links": [], "nodes": [], "directed": True, "multigraph": False, "graph": {}}}
        )
        mgr.update_snapshot(replacement)
        assert mgr.current.relationships_snapshot is not sample_world_state.relationships_snapshot

        restored = mgr.undo()
        assert restored is not None
        assert restored.turn == 0
