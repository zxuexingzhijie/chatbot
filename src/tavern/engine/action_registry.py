from __future__ import annotations

from typing import TYPE_CHECKING

from tavern.engine.action_defs import ActionDef
from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest, ActionResult

if TYPE_CHECKING:
    from tavern.world.state import StateDiff, WorldState


class ActionRegistry:
    def __init__(self, actions: list[ActionDef]) -> None:
        self._actions: dict[ActionType, ActionDef] = {a.action_type: a for a in actions}

    def get(self, action_type: ActionType) -> ActionDef | None:
        return self._actions.get(action_type)

    def get_available_actions(self, state: WorldState) -> list[ActionDef]:
        return [a for a in self._actions.values() if a.is_available(state)]

    def get_valid_targets(
        self, action_type: ActionType, state: WorldState,
    ) -> list[str]:
        action = self._actions.get(action_type)
        return action.valid_targets(state) if action else []

    def validate_and_execute(
        self, request: ActionRequest, state: WorldState,
    ) -> tuple[ActionResult, StateDiff | None]:
        action = self._actions.get(request.action)
        if not action:
            return ActionResult(
                success=False, action=request.action, message="未知动作",
            ), None
        if not action.is_available(state):
            return ActionResult(
                success=False, action=request.action, message="当前无法执行此动作",
            ), None
        if action.requires_target and request.target not in action.valid_targets(state):
            return ActionResult(
                success=False, action=request.action,
                message=f"无效目标: {request.target}",
            ), None
        return action.handler(request, state)
