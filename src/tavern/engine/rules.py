from __future__ import annotations

import logging
import uuid

from tavern.engine.actions import ActionType
from tavern.engine.use_effects import USE_EFFECT_REGISTRY
from tavern.world.models import ActionRequest, ActionResult, Event
from tavern.world.state import StateDiff, WorldState

logger = logging.getLogger(__name__)


class RulesEngine:
    def validate(
        self, request: ActionRequest, state: WorldState
    ) -> tuple[ActionResult, StateDiff | None]:
        handler = _ACTION_HANDLERS.get(request.action, _handle_custom)
        return handler(request, state)


def _get_player(state: WorldState):
    return state.characters[state.player_id]


def _get_player_location(state: WorldState):
    player = _get_player(state)
    return state.locations[player.location_id]


def _handle_move(request: ActionRequest, state: WorldState):
    location = _get_player_location(state)
    player = _get_player(state)
    direction = request.target

    if direction not in location.exits:
        available = ", ".join(location.exits.keys())
        return (
            ActionResult(
                success=False,
                action=ActionType.MOVE,
                message=f"这里没有通往「{direction}」的出口。可用方向: {available}",
                target=direction,
            ),
            None,
        )

    exit_ = location.exits[direction]

    if exit_.locked:
        if exit_.key_item and exit_.key_item in player.inventory:
            return _unlock_and_move(state, location, exit_, direction)
        target_loc = state.locations[exit_.target]
        return (
            ActionResult(
                success=False,
                action=ActionType.MOVE,
                message=f"通往{target_loc.name}的门被锁住了。{exit_.description}",
                target=direction,
            ),
            None,
        )

    target_loc = state.locations[exit_.target]
    diff = StateDiff(
        updated_characters={state.player_id: {"location_id": exit_.target}}
    )
    return (
        ActionResult(
            success=True,
            action=ActionType.MOVE,
            message=f"你走向{target_loc.name}。\n\n{target_loc.description}",
            target=exit_.target,
        ),
        diff,
    )


def _unlock_and_move(state, location, exit_, direction):
    new_exits = dict(location.exits)
    new_exits[direction] = exit_.model_copy(update={"locked": False})
    target_loc = state.locations[exit_.target]

    key_name = state.items[exit_.key_item].name if exit_.key_item in state.items else exit_.key_item
    event = Event(
        id=f"evt_{uuid.uuid4().hex[:8]}",
        turn=state.turn,
        type="unlock",
        actor=state.player_id,
        description=f"用{key_name}打开了通往{target_loc.name}的门",
    )

    diff = StateDiff(
        updated_characters={state.player_id: {"location_id": exit_.target}},
        updated_locations={location.id: {"exits": new_exits}},
        new_events=(event,),
    )
    return (
        ActionResult(
            success=True,
            action=ActionType.MOVE,
            message=f"你用钥匙打开了门，走进了{target_loc.name}。\n\n{target_loc.description}",
            target=exit_.target,
        ),
        diff,
    )


def _handle_look(request: ActionRequest, state: WorldState):
    location = _get_player_location(state)

    if request.target is None:
        return _look_at_location(state, location)

    return _look_at_target(request.target, state, location)


def _look_at_location(state, location):
    parts = [f"【{location.name}】", location.description]

    if location.npcs:
        npc_names = [
            state.characters[npc_id].name
            for npc_id in location.npcs
            if npc_id in state.characters
        ]
        if npc_names:
            parts.append(f"在场人物: {', '.join(npc_names)}")

    if location.items:
        item_names = [
            state.items[item_id].name
            for item_id in location.items
            if item_id in state.items
        ]
        if item_names:
            parts.append(f"可见物品: {', '.join(item_names)}")

    if location.exits:
        exit_descs = [f"  {d}: {e.description}" for d, e in location.exits.items()]
        parts.append("出口:\n" + "\n".join(exit_descs))

    return (
        ActionResult(
            success=True, action=ActionType.LOOK, message="\n".join(parts)
        ),
        None,
    )


def _look_at_target(target_id, state, location):
    if target_id in location.items and target_id in state.items:
        item = state.items[target_id]
        return (
            ActionResult(
                success=True,
                action=ActionType.LOOK,
                message=f"【{item.name}】\n{item.description}",
                target=target_id,
            ),
            None,
        )

    player = _get_player(state)
    if target_id in player.inventory and target_id in state.items:
        item = state.items[target_id]
        return (
            ActionResult(
                success=True,
                action=ActionType.LOOK,
                message=f"【{item.name}】（背包中）\n{item.description}",
                target=target_id,
            ),
            None,
        )

    if target_id in location.npcs and target_id in state.characters:
        npc = state.characters[target_id]
        traits_desc = "、".join(npc.traits) if npc.traits else "难以捉摸"
        return (
            ActionResult(
                success=True,
                action=ActionType.LOOK,
                message=f"【{npc.name}】\n{traits_desc}",
                target=target_id,
            ),
            None,
        )

    return (
        ActionResult(
            success=False,
            action=ActionType.LOOK,
            message=f"你没有看到「{target_id}」。",
            target=target_id,
        ),
        None,
    )


def _handle_take(request: ActionRequest, state: WorldState):
    location = _get_player_location(state)
    player = _get_player(state)
    target_id = request.target

    if target_id is None:
        return (
            ActionResult(
                success=False, action=ActionType.TAKE, message="你想拾取什么？"
            ),
            None,
        )

    if target_id not in location.items:
        return (
            ActionResult(
                success=False,
                action=ActionType.TAKE,
                message=f"这里没有「{target_id}」可以拾取。",
                target=target_id,
            ),
            None,
        )

    if target_id not in state.items:
        return (
            ActionResult(
                success=False,
                action=ActionType.TAKE,
                message=f"未知物品: {target_id}",
                target=target_id,
            ),
            None,
        )

    item = state.items[target_id]

    if not item.portable:
        return (
            ActionResult(
                success=False,
                action=ActionType.TAKE,
                message=f"「{item.name}」太重了，无法拾取。",
                target=target_id,
            ),
            None,
        )

    new_inventory = player.inventory + (target_id,)
    new_location_items = tuple(i for i in location.items if i != target_id)

    event = Event(
        id=f"evt_{uuid.uuid4().hex[:8]}",
        turn=state.turn,
        type="take",
        actor=state.player_id,
        description=f"拾取了{item.name}",
    )

    diff = StateDiff(
        updated_characters={state.player_id: {"inventory": new_inventory}},
        updated_locations={location.id: {"items": new_location_items}},
        new_events=(event,),
        turn_increment=0,
    )
    return (
        ActionResult(
            success=True,
            action=ActionType.TAKE,
            message=f"你拾取了「{item.name}」。",
            target=target_id,
        ),
        diff,
    )


def _handle_talk(request: ActionRequest, state: WorldState):
    target_id = request.target
    if target_id is None:
        return (
            ActionResult(
                success=False, action=ActionType.TALK, message="你想和谁说话？"
            ),
            None,
        )

    if target_id not in state.characters:
        return (
            ActionResult(
                success=False,
                action=ActionType.TALK,
                message=f"这里没有叫「{target_id}」的人。",
                target=target_id,
            ),
            None,
        )

    location = _get_player_location(state)
    if target_id not in location.npcs:
        npc_name = state.characters[target_id].name
        return (
            ActionResult(
                success=False,
                action=ActionType.TALK,
                message=f"{npc_name}不在这里。",
                target=target_id,
            ),
            None,
        )

    npc_name = state.characters[target_id].name
    return (
        ActionResult(
            success=True,
            action=ActionType.TALK,
            message=f"你走向{npc_name}，准备交谈。",
            target=target_id,
        ),
        None,
    )


def _handle_custom(request: ActionRequest, state: WorldState):
    detail = request.detail or "某些事情"
    return (
        ActionResult(
            success=True,
            action=ActionType.CUSTOM,
            message=f"你尝试{detail}，但结果不太明朗。",
            detail=request.detail,
        ),
        None,
    )


def _handle_use(request: ActionRequest, state: WorldState):
    item_id = request.target

    if item_id is None:
        return (
            ActionResult(success=False, action=ActionType.USE, message="你想使用什么？"),
            None,
        )

    player = _get_player(state)
    location = _get_player_location(state)
    if item_id not in player.inventory and item_id not in location.items:
        return (
            ActionResult(success=False, action=ActionType.USE,
                         message="你没有那个物品。", target=item_id),
            None,
        )

    if item_id not in state.items:
        return (
            ActionResult(success=False, action=ActionType.USE,
                         message=f"未知物品: {item_id}", target=item_id),
            None,
        )

    item = state.items[item_id]

    if item.usable_with:
        if request.detail is None:
            return (
                ActionResult(success=False, action=ActionType.USE,
                             message="你想把它用在什么上？", target=item_id),
                None,
            )
        if request.detail not in item.usable_with:
            return (
                ActionResult(success=False, action=ActionType.USE,
                             message="该物品不能用在这里。", target=item_id),
                None,
            )

    if not item.use_effects:
        return (
            ActionResult(success=False, action=ActionType.USE,
                         message=f"「{item.name}」无法使用。", target=item_id),
            None,
        )

    combined_diff = StateDiff(turn_increment=1)
    messages = []
    current_state = state
    any_executed = False
    for eff in item.use_effects:
        fn = USE_EFFECT_REGISTRY.get(eff.type)
        if fn is None:
            logger.warning("未知 use_effect 类型: %s（物品: %s）", eff.type, item_id)
            continue
        diff, msg = fn(eff, item_id, current_state)
        any_executed = True
        combined_diff = _merge_diffs(combined_diff, diff)
        current_state = current_state.apply(diff)
        if msg:
            messages.append(msg)

    if not any_executed:
        return (
            ActionResult(success=False, action=ActionType.USE,
                         message=f"「{item.name}」无法使用。", target=item_id),
            None,
        )

    final_message = "\n".join(messages) if messages else f"你使用了「{item.name}」。"
    return (
        ActionResult(success=True, action=ActionType.USE,
                     message=final_message, target=item_id),
        combined_diff,
    )


def _merge_diffs(a: StateDiff, b: StateDiff) -> StateDiff:
    def _deep_merge(x: dict, y: dict) -> dict:
        result = dict(x)
        for k, v in y.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = _deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def _merge_stat_deltas(x: dict, y: dict) -> dict:
        result = {char_id: dict(stats) for char_id, stats in x.items()}
        for char_id, stats in y.items():
            if char_id not in result:
                result[char_id] = dict(stats)
            else:
                for stat, val in stats.items():
                    result[char_id][stat] = result[char_id].get(stat, 0) + val
        return result

    return StateDiff(
        updated_characters=_deep_merge(a.updated_characters, b.updated_characters),
        updated_locations=_deep_merge(a.updated_locations, b.updated_locations),
        added_items={**a.added_items, **b.added_items},
        removed_items=a.removed_items + b.removed_items,
        relationship_changes=a.relationship_changes + b.relationship_changes,
        quest_updates={**a.quest_updates, **b.quest_updates},
        new_events=a.new_events + b.new_events,
        new_endings=a.new_endings + b.new_endings,
        story_active_since_updates={**a.story_active_since_updates, **b.story_active_since_updates},
        character_stat_deltas=_merge_stat_deltas(a.character_stat_deltas, b.character_stat_deltas),
        turn_increment=a.turn_increment + b.turn_increment,
    )


def _handle_search(request: ActionRequest, state: WorldState):
    location = _get_player_location(state)

    if request.target is not None:
        return _look_at_target(request.target, state, location)

    result, _ = _look_at_location(state, location)
    event = Event(
        id=f"searched_{location.id}",
        turn=state.turn,
        type="search",
        actor=state.player_id,
        description=f"仔细搜索了{location.name}",
    )
    diff = StateDiff(new_events=(event,), turn_increment=0)
    return result, diff


_ACTION_HANDLERS = {
    ActionType.MOVE: _handle_move,
    ActionType.LOOK: _handle_look,
    ActionType.SEARCH: _handle_search,
    ActionType.TAKE: _handle_take,
    ActionType.TALK: _handle_talk,
    ActionType.PERSUADE: _handle_talk,
    ActionType.USE: _handle_use,
    ActionType.CUSTOM: _handle_custom,
}
