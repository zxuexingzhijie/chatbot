from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavern.engine.fsm import EffectExecutor, EffectKind
from tavern.world.state import StateDiff

if TYPE_CHECKING:
    from tavern.engine.fsm import ModeContext

logger = logging.getLogger(__name__)


def _render_quest_notifications(diff: StateDiff, old_state, ctx: "ModeContext") -> None:
    from tavern.engine.quest_descriptions import (
        get_quest_display_name,
        get_quest_status_description,
        should_notify,
    )
    renderer = ctx.renderer
    if not hasattr(renderer, "render_quest_notification"):
        return
    for quest_id, updates in diff.quest_updates.items():
        status = updates.get("status")
        if status is None:
            continue
        old_quest = old_state.quests.get(quest_id, {})
        if old_quest.get("status") == status:
            continue
        if not should_notify(quest_id, status):
            continue
        display_name = get_quest_display_name(quest_id)
        description = get_quest_status_description(quest_id, status)
        renderer.render_quest_notification(display_name, status, description)


async def exec_start_dialogue(payload: dict, ctx: ModeContext) -> None:
    npc_id = payload["npc_id"]
    state = ctx.state_manager.state
    npc = state.characters.get(npc_id)
    if npc is None:
        logger.warning("NPC not found: %s", npc_id)
        await ctx.renderer.render_error(f"找不到NPC: {npc_id}")
        return
    memory_ctx = None
    if hasattr(ctx.memory, "build_context"):
        memory_ctx = ctx.memory.build_context(actor=npc_id, state=state)
    dialogue_ctx, response = await ctx.dialogue_manager.start(
        state, npc_id, memory_ctx=memory_ctx,
    )
    ctx.renderer.render_dialogue_start(dialogue_ctx, response)
    await ctx.renderer.render_dialogue_streaming(response.text)
    logger.info("Starting dialogue with %s", npc_id)


async def exec_end_dialogue(payload: dict, ctx: ModeContext) -> None:
    if hasattr(ctx.dialogue_manager, "reset"):
        ctx.dialogue_manager.reset()
    logger.info("Ending dialogue")


async def exec_apply_diff(payload: dict, ctx: ModeContext) -> None:
    diff = payload["diff"]
    action = payload.get("action")
    old_state = ctx.state_manager.state
    new_state = ctx.state_manager.commit(diff, action)
    if hasattr(ctx.memory, "apply_diff"):
        ctx.memory.apply_diff(diff, new_state)
    if hasattr(ctx.memory, "sync_to_state") and hasattr(ctx.state_manager, "update_snapshot"):
        synced = ctx.memory.sync_to_state(new_state)
        ctx.state_manager.update_snapshot(synced)
    _render_quest_notifications(diff, old_state, ctx)


async def exec_emit_event(payload: dict, ctx: ModeContext) -> None:
    event = payload["event"]
    if ctx.story_engine is not None and hasattr(ctx.story_engine, "check"):
        state = ctx.state_manager.state
        timeline = context_timeline(ctx)
        relationships = context_relationships(ctx)
        ctx.story_engine.check(state, "passive", timeline, relationships)
    logger.info("Event emitted: %s", event)


def context_timeline(ctx: ModeContext):
    return ctx.memory.timeline if hasattr(ctx.memory, "timeline") else ()


def context_relationships(ctx: ModeContext):
    return ctx.memory.relationship_graph if hasattr(ctx.memory, "relationship_graph") else {}


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
    new_state = ctx.state_manager.commit(trust_diff, None)
    if hasattr(ctx.memory, "apply_diff"):
        ctx.memory.apply_diff(trust_diff, new_state)
    if hasattr(ctx.memory, "sync_to_state") and hasattr(ctx.state_manager, "update_snapshot"):
        synced = ctx.memory.sync_to_state(new_state)
        ctx.state_manager.update_snapshot(synced)
    logger.info("Applied trust delta %+d to %s (now %d)", delta, npc_id, new_trust)


async def exec_open_shop(payload: dict, ctx: ModeContext) -> None:
    logger.info("Opening shop: %s", payload)


EFFECT_EXECUTORS: dict[EffectKind, EffectExecutor] = {
    EffectKind.START_DIALOGUE: exec_start_dialogue,
    EffectKind.END_DIALOGUE: exec_end_dialogue,
    EffectKind.APPLY_DIFF: exec_apply_diff,
    EffectKind.EMIT_EVENT: exec_emit_event,
    EffectKind.APPLY_TRUST: exec_apply_trust,
    EffectKind.OPEN_SHOP: exec_open_shop,
}
