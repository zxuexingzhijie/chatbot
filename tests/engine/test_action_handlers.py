from __future__ import annotations

import pytest

from tavern.engine.action_handlers import build_all_actions
from tavern.engine.action_registry import ActionRegistry
from tavern.engine.actions import ActionType
from tavern.world.models import (
    ActionRequest, ActionResult, Character, CharacterRole, Exit, Item, Location,
)
from tavern.world.state import WorldState


def _make_state(**overrides) -> WorldState:
    defaults = dict(
        turn=0,
        player_id="player",
        locations={
            "hall": Location(
                id="hall", name="大厅", description="大厅",
                exits={"north": Exit(target="cellar")},
                items=("old_notice",),
                npcs=("bartender",),
            ),
            "cellar": Location(id="cellar", name="地窖", description="地窖"),
        },
        characters={
            "player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="hall",
            ),
            "bartender": Character(
                id="bartender", name="格里姆", role=CharacterRole.NPC,
                location_id="hall",
            ),
        },
        items={
            "old_notice": Item(
                id="old_notice", name="旧告示", description="一张旧告示",
                portable=True,
            ),
        },
    )
    defaults.update(overrides)
    return WorldState(**defaults)


class TestBuildAllActions:
    def test_returns_list_of_action_defs(self):
        actions = build_all_actions()
        assert len(actions) >= 6

    def test_all_have_action_type(self):
        actions = build_all_actions()
        for a in actions:
            assert a.action_type is not None

    def test_no_duplicate_action_types(self):
        actions = build_all_actions()
        types = [a.action_type for a in actions]
        assert len(types) == len(set(types))


class TestMoveAction:
    def test_is_available_with_exits(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        move = registry.get(ActionType.MOVE)
        assert move.is_available(state) is True

    def test_is_available_without_exits(self):
        state = WorldState(
            player_id="player",
            locations={"room": Location(id="room", name="R", description="d")},
            characters={"player": Character(
                id="player", name="P", role=CharacterRole.PLAYER,
                location_id="room",
            )},
        )
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        move = registry.get(ActionType.MOVE)
        assert move.is_available(state) is False

    def test_valid_targets_are_exit_directions(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        targets = registry.get_valid_targets(ActionType.MOVE, state)
        assert "north" in targets

    def test_handler_produces_diff(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        req = ActionRequest(action=ActionType.MOVE, target="north")
        result, diff = registry.validate_and_execute(req, state)
        assert result.success is True
        assert diff is not None


class TestLookAction:
    def test_is_always_available(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        look = registry.get(ActionType.LOOK)
        assert look.is_available(state) is True

    def test_does_not_require_target(self):
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        look = registry.get(ActionType.LOOK)
        assert look.requires_target is False


class TestTalkAction:
    def test_valid_targets_are_npcs_in_location(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        targets = registry.get_valid_targets(ActionType.TALK, state)
        assert "bartender" in targets
        assert "player" not in targets

    def test_is_available_when_npcs_present(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        talk = registry.get(ActionType.TALK)
        assert talk.is_available(state) is True


class TestTakeAction:
    def test_valid_targets_are_location_items(self):
        state = _make_state()
        actions = build_all_actions()
        registry = ActionRegistry(actions)
        targets = registry.get_valid_targets(ActionType.TAKE, state)
        assert "old_notice" in targets
