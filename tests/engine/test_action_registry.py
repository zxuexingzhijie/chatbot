from __future__ import annotations

import pytest

from tavern.engine.action_defs import ActionDef, build_action
from tavern.engine.action_registry import ActionRegistry
from tavern.engine.actions import ActionType
from tavern.world.models import (
    ActionRequest, ActionResult, Character, CharacterRole, Exit, Location,
)
from tavern.world.state import StateDiff, WorldState


def _make_state(**kwargs) -> WorldState:
    defaults = dict(
        turn=0,
        player_id="player",
        locations={
            "hall": Location(
                id="hall", name="大厅", description="大厅",
                exits={"north": Exit(target="cellar")},
                npcs=("npc1",),
            ),
            "cellar": Location(id="cellar", name="地窖", description="地窖"),
        },
        characters={
            "player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="hall",
            ),
            "npc1": Character(
                id="npc1", name="NPC", role=CharacterRole.NPC,
                location_id="hall",
            ),
        },
    )
    defaults.update(kwargs)
    return WorldState(**defaults)


def _handle_move(req: ActionRequest, state: WorldState):
    return (
        ActionResult(success=True, action=ActionType.MOVE, message="moved"),
        StateDiff(updated_characters={state.player_id: {"location_id": req.target}}),
    )


def _handle_look(req: ActionRequest, state: WorldState):
    return (
        ActionResult(success=True, action=ActionType.LOOK, message="looked"),
        None,
    )


def _make_registry() -> ActionRegistry:
    move = build_action(
        action_type=ActionType.MOVE,
        description="移动",
        requires_target=True,
        valid_targets=lambda s: list(s.current_location.exits.keys()),
        is_available=lambda s: len(s.current_location.exits) > 0,
        handler=_handle_move,
    )
    look = build_action(
        action_type=ActionType.LOOK,
        description="查看",
        requires_target=False,
        handler=_handle_look,
    )
    return ActionRegistry([move, look])


class TestActionRegistry:
    def test_get_available_actions(self):
        state = _make_state()
        reg = _make_registry()
        available = reg.get_available_actions(state)
        types = [a.action_type for a in available]
        assert ActionType.MOVE in types
        assert ActionType.LOOK in types

    def test_get_available_actions_filters_unavailable(self):
        state = WorldState(
            player_id="player",
            locations={"room": Location(id="room", name="R", description="d")},
            characters={"player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="room",
            )},
        )
        reg = _make_registry()
        available = reg.get_available_actions(state)
        types = [a.action_type for a in available]
        assert ActionType.MOVE not in types
        assert ActionType.LOOK in types

    def test_get_valid_targets(self):
        state = _make_state()
        reg = _make_registry()
        targets = reg.get_valid_targets(ActionType.MOVE, state)
        assert "north" in targets

    def test_get_valid_targets_unknown_action(self):
        state = _make_state()
        reg = _make_registry()
        assert reg.get_valid_targets(ActionType.CUSTOM, state) == []

    def test_validate_and_execute_success(self):
        state = _make_state()
        reg = _make_registry()
        req = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = reg.validate_and_execute(req, state)
        assert result.success is True
        assert diff is not None

    def test_validate_and_execute_unknown_action(self):
        state = _make_state()
        reg = _make_registry()
        req = ActionRequest(action=ActionType.CUSTOM, target="npc1")
        result, diff = reg.validate_and_execute(req, state)
        assert result.success is False
        assert "未知动作" in result.message

    def test_validate_and_execute_unavailable(self):
        state = WorldState(
            player_id="player",
            locations={"room": Location(id="room", name="R", description="d")},
            characters={"player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="room",
            )},
        )
        reg = _make_registry()
        req = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = reg.validate_and_execute(req, state)
        assert result.success is False

    def test_validate_and_execute_invalid_target(self):
        state = _make_state()
        reg = _make_registry()
        req = ActionRequest(action=ActionType.MOVE, target="nonexistent")
        result, diff = reg.validate_and_execute(req, state)
        assert result.success is False
        assert "无效目标" in result.message

    def test_validate_and_execute_no_target_required(self):
        state = _make_state()
        reg = _make_registry()
        req = ActionRequest(action=ActionType.LOOK)
        result, diff = reg.validate_and_execute(req, state)
        assert result.success is True
