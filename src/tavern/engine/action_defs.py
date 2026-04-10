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
    description_fn: Callable[["WorldState"], str] | None
    valid_targets: Callable[["WorldState"], list[str]]
    is_available: Callable[["WorldState"], bool]
    handler: Handler
    requires_target: bool = True
    cooldown_turns: int = 0


def _default_handler(req: ActionRequest, state: WorldState) -> tuple[ActionResult, StateDiff | None]:
    return ActionResult(success=True, action=req.action, message=""), None


ACTION_DEFAULTS = ActionDef(
    action_type=ActionType.CUSTOM,
    description="自定义动作",
    description_fn=None,
    valid_targets=lambda s: [],
    is_available=lambda s: True,
    handler=_default_handler,
    requires_target=False,
    cooldown_turns=0,
)


def build_action(**overrides) -> ActionDef:
    return dataclasses.replace(ACTION_DEFAULTS, **overrides)
