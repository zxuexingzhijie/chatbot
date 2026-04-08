from __future__ import annotations

import logging
from typing import Callable

from tavern.world.models import Event, UseEffect
from tavern.world.state import StateDiff, WorldState

logger = logging.getLogger(__name__)

UseEffectFn = Callable[[UseEffect, str, WorldState], tuple[StateDiff, str | None]]

USE_EFFECT_REGISTRY: dict[str, UseEffectFn] = {}


def register_effect(type_name: str):
    def decorator(fn: UseEffectFn) -> UseEffectFn:
        USE_EFFECT_REGISTRY[type_name] = fn
        return fn
    return decorator


@register_effect("unlock")
def effect_unlock(eff: UseEffect, item_id: str, state: WorldState) -> tuple[StateDiff, str | None]:
    if eff.location is None or eff.exit_direction is None:
        logger.warning("unlock effect missing location or exit_direction (item: %s)", item_id)
        return StateDiff(turn_increment=0), None

    location = state.locations.get(eff.location)
    if location is None:
        logger.warning("unlock effect: location %r not found (item: %s)", eff.location, item_id)
        return StateDiff(turn_increment=0), None

    exit_ = location.exits.get(eff.exit_direction)
    if exit_ is None:
        logger.warning("unlock effect: exit %r not found in %r (item: %s)", eff.exit_direction, eff.location, item_id)
        return StateDiff(turn_increment=0), None

    new_exits = {**dict(location.exits), eff.exit_direction: exit_.model_copy(update={"locked": False})}
    diff = StateDiff(
        updated_locations={eff.location: {"exits": new_exits}},
        turn_increment=0,
    )
    target_loc = state.locations.get(exit_.target)
    target_name = target_loc.name if target_loc else exit_.target
    return diff, f"门被打开了，通往{target_name}。"


@register_effect("consume")
def effect_consume(eff: UseEffect, item_id: str, state: WorldState) -> tuple[StateDiff, str | None]:
    player = state.characters[state.player_id]
    if item_id not in player.inventory:
        logger.warning("consume effect: item %r not in player inventory", item_id)
        return StateDiff(turn_increment=0), None
    new_inventory = tuple(i for i in player.inventory if i != item_id)
    diff = StateDiff(
        updated_characters={state.player_id: {"inventory": new_inventory}},
        turn_increment=0,
    )
    return diff, None


@register_effect("spawn_item")
def effect_spawn_item(eff: UseEffect, item_id: str, state: WorldState) -> tuple[StateDiff, str | None]:
    if eff.item_id is None:
        logger.warning("spawn_item effect missing item_id (item: %s)", item_id)
        return StateDiff(turn_increment=0), None

    if eff.item_id not in state.items:
        logger.warning("spawn_item effect: item_id %r not in state.items (item: %s)", eff.item_id, item_id)
        return StateDiff(turn_increment=0), None

    spawned = state.items[eff.item_id]

    if eff.spawn_to_inventory:
        player = state.characters[state.player_id]
        new_inventory = player.inventory + (eff.item_id,)
        diff = StateDiff(
            updated_characters={state.player_id: {"inventory": new_inventory}},
            turn_increment=0,
        )
        return diff, f"你获得了「{spawned.name}」。"
    else:
        if eff.location is None:
            logger.warning("spawn_item effect: spawn_to_inventory=False but no location (item: %s)", item_id)
            return StateDiff(turn_increment=0), None
        loc = state.locations.get(eff.location)
        if loc is None:
            logger.warning("spawn_item effect: location %r not found (item: %s)", eff.location, item_id)
            return StateDiff(turn_increment=0), None
        new_items = loc.items + (eff.item_id,)
        diff = StateDiff(
            updated_locations={eff.location: {"items": new_items}},
            turn_increment=0,
        )
        loc_name = loc.name
        return diff, f"「{spawned.name}」出现在了{loc_name}。"


@register_effect("story_event")
def effect_story_event(eff: UseEffect, item_id: str, state: WorldState) -> tuple[StateDiff, str | None]:
    if eff.event is None:
        logger.warning("story_event effect missing event spec (item: %s)", item_id)
        return StateDiff(turn_increment=0), None

    actor = eff.event.actor or state.player_id
    event = Event(
        id=f"{eff.event.id}_t{state.turn}",
        turn=state.turn,
        type=eff.event.type,
        actor=actor,
        description=eff.event.description,
    )
    diff = StateDiff(new_events=(event,), turn_increment=0)
    return diff, None
