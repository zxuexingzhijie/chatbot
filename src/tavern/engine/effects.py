from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavern.engine.fsm import EffectExecutor, EffectKind
from tavern.world.state import StateDiff

if TYPE_CHECKING:
    from tavern.engine.fsm import ModeContext

logger = logging.getLogger(__name__)


async def exec_start_dialogue(payload: dict, ctx: ModeContext) -> None:
    npc_id = payload["npc_id"]
    state = ctx.state_manager.state
    npc = state.characters.get(npc_id)
    if npc is None:
        raise ValueError(f"NPC not found: {npc_id}")
    if hasattr(ctx.dialogue_manager, "set_active_npc"):
        ctx.dialogue_manager.set_active_npc(npc_id)
    logger.info("Starting dialogue with %s", npc_id)


async def exec_end_dialogue(payload: dict, ctx: ModeContext) -> None:
    if hasattr(ctx.dialogue_manager, "reset"):
        ctx.dialogue_manager.reset()
    logger.info("Ending dialogue")


async def exec_apply_diff(payload: dict, ctx: ModeContext) -> None:
    diff = payload["diff"]
    action = payload.get("action")
    ctx.state_manager.commit(diff, action)


async def exec_emit_event(payload: dict, ctx: ModeContext) -> None:
    event = payload["event"]
    if ctx.story_engine is not None and hasattr(ctx.story_engine, "check"):
        state = ctx.state_manager.state
        ctx.story_engine.check(state, state.timeline, ctx.memory.graph)
    logger.info("Event emitted: %s", event)


async def exec_apply_trust(payload: dict, ctx: ModeContext) -> None:
    npc_id = payload["npc_id"]
    delta = payload["delta"]
    state = ctx.state_manager.state
    npc = state.characters[npc_id]
    old_trust = int(npc.stats.get("trust", 0))
    new_trust = max(-100, min(100, old_trust + delta))
    new_stats = {**dict(npc.stats), "trust": new_trust}
    trust_diff = StateDiff(
        updated_characters={npc_id: {"stats": new_stats}},
        relationship_changes=(
            {"src": state.player_id, "tgt": npc_id, "delta": delta},
        ),
        turn_increment=0,
    )
    ctx.state_manager.commit(trust_diff, None)
    logger.info("Applied trust delta %+d to %s (now %d)", delta, npc_id, new_trust)


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
