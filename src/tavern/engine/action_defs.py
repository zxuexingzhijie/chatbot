from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest, ActionResult

if TYPE_CHECKING:
    from tavern.world.state import StateDiff, WorldState

Handler = Callable[["ActionRequest", "WorldState"], tuple["ActionResult", "StateDiff | None"]]


@dataclass(frozen=True)
class ActionDef:
    action_type: ActionType
    description: str
    valid_targets: Callable[["WorldState"], list[str]]
    is_available: Callable[["WorldState"], bool]
    handler: Handler
    requires_target: bool = True
    description_fn: Callable[["WorldState"], str] | None = None
    cooldown_turns: int = 0


def _default_handler(req: ActionRequest, state: WorldState) -> tuple[ActionResult, StateDiff | None]:
    return ActionResult(success=True, action=req.action, message=""), None


ACTION_DEFAULTS = ActionDef(
    action_type=ActionType.CUSTOM,
    description="自定义动作",
    valid_targets=lambda s: [],
    is_available=lambda s: True,
    handler=_default_handler,
    requires_target=False,
)


def build_action(**overrides) -> ActionDef:
    return dataclasses.replace(ACTION_DEFAULTS, **overrides)
