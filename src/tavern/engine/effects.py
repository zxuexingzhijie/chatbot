from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavern.engine.fsm import EffectExecutor, EffectKind

if TYPE_CHECKING:
    from tavern.engine.fsm import ModeContext

logger = logging.getLogger(__name__)


async def exec_start_dialogue(payload: dict, ctx: ModeContext) -> None:
    npc_id = payload["npc_id"]
    state = ctx.state_manager.state
    npc = state.characters.get(npc_id)
    if npc is None:
        raise ValueError(f"NPC not found: {npc_id}")
    logger.info("Starting dialogue with %s", npc_id)


async def exec_end_dialogue(payload: dict, ctx: ModeContext) -> None:
    logger.info("Ending dialogue")


async def exec_apply_diff(payload: dict, ctx: ModeContext) -> None:
    diff = payload["diff"]
    action = payload.get("action")
    ctx.state_manager.commit(diff, action)


async def exec_emit_event(payload: dict, ctx: ModeContext) -> None:
    event = payload["event"]
    logger.info("Event emitted: %s", event)


async def exec_apply_trust(payload: dict, ctx: ModeContext) -> None:
    logger.info("Applying trust changes: %s", payload)


async def exec_init_combat(payload: dict, ctx: ModeContext) -> None:
    logger.info("Initializing combat: %s", payload)


async def exec_apply_rewards(payload: dict, ctx: ModeContext) -> None:
    logger.info("Applying rewards: %s", payload)


async def exec_flee_penalty(payload: dict, ctx: ModeContext) -> None:
    logger.info("Applying flee penalty: %s", payload)


async def exec_open_shop(payload: dict, ctx: ModeContext) -> None:
    logger.info("Opening shop: %s", payload)


EFFECT_EXECUTORS: dict[EffectKind, EffectExecutor] = {
    EffectKind.START_DIALOGUE: exec_start_dialogue,
    EffectKind.END_DIALOGUE: exec_end_dialogue,
    EffectKind.APPLY_DIFF: exec_apply_diff,
    EffectKind.EMIT_EVENT: exec_emit_event,
    EffectKind.APPLY_TRUST: exec_apply_trust,
    EffectKind.INIT_COMBAT: exec_init_combat,
    EffectKind.APPLY_REWARDS: exec_apply_rewards,
    EffectKind.FLEE_PENALTY: exec_flee_penalty,
    EffectKind.OPEN_SHOP: exec_open_shop,
}
