import dataclasses

import pytest

from tavern.engine.action_defs import ActionDef, build_action, ACTION_DEFAULTS
from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest, ActionResult
from tavern.world.state import StateDiff


class TestActionDef:
    def test_defaults_has_custom_type(self):
        assert ACTION_DEFAULTS.action_type == ActionType.CUSTOM

    def test_defaults_is_available_returns_true(self):
        assert ACTION_DEFAULTS.is_available(None) is True

    def test_defaults_valid_targets_returns_empty(self):
        assert ACTION_DEFAULTS.valid_targets(None) == []

    def test_defaults_handler_returns_success(self):
        req = ActionRequest(action=ActionType.CUSTOM)
        result, diff = ACTION_DEFAULTS.handler(req, None)
        assert result.success is True
        assert diff is None

    def test_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            ACTION_DEFAULTS.action_type = ActionType.MOVE


class TestBuildAction:
    def test_override_action_type(self):
        action = build_action(action_type=ActionType.MOVE)
        assert action.action_type == ActionType.MOVE
        assert action.description == ACTION_DEFAULTS.description

    def test_override_handler(self):
        def custom_handler(req, state):
            return ActionResult(success=True, action=req.action, message="custom"), None

        action = build_action(
            action_type=ActionType.LOOK,
            handler=custom_handler,
        )
        req = ActionRequest(action=ActionType.LOOK)
        result, diff = action.handler(req, None)
        assert result.message == "custom"

    def test_override_is_available(self):
        action = build_action(is_available=lambda s: False)
        assert action.is_available(None) is False

    def test_override_valid_targets(self):
        action = build_action(valid_targets=lambda s: ["a", "b"])
        assert action.valid_targets(None) == ["a", "b"]

    def test_override_requires_target(self):
        action = build_action(requires_target=True)
        assert action.requires_target is True

    def test_override_description(self):
        action = build_action(description="测试动作")
        assert action.description == "测试动作"

    def test_build_preserves_defaults_for_unset_fields(self):
        action = build_action(action_type=ActionType.MOVE, description="移动")
        assert action.cooldown_turns == 0
        assert action.description_fn is None
