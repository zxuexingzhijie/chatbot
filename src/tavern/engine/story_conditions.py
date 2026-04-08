from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from tavern.world.skills import ActivationCondition, ConditionEvaluator

if TYPE_CHECKING:
    from tavern.world.memory import EventTimeline, RelationshipGraph
    from tavern.world.state import WorldState

logger = logging.getLogger(__name__)

ConditionEvaluatorFn = Callable[
    [ActivationCondition, "WorldState", "EventTimeline", "RelationshipGraph"],
    bool,
]

# ActivationCondition field conventions for story conditions:
#   event_id  — canonical "string value" field used by all non-relationship evaluators
#               (location target, item id, event id, quest id)
#   operator / value — used only by relationship conditions (numeric comparison)
CONDITION_REGISTRY: dict[str, ConditionEvaluatorFn] = {}


def register_condition(type_name: str):
    def decorator(fn: ConditionEvaluatorFn) -> ConditionEvaluatorFn:
        CONDITION_REGISTRY[type_name] = fn
        return fn
    return decorator


@register_condition("location")
def eval_location(cond: ActivationCondition, state: "WorldState", timeline, relationships) -> bool:
    player = state.characters.get(state.player_id)
    if player is None:
        return False
    return player.location_id == cond.event_id


@register_condition("inventory")
def eval_inventory(cond: ActivationCondition, state: "WorldState", timeline, relationships) -> bool:
    return ConditionEvaluator.evaluate(cond, state, timeline, relationships)


@register_condition("relationship")
def eval_relationship(cond: ActivationCondition, state, timeline, relationships: "RelationshipGraph") -> bool:
    return ConditionEvaluator.evaluate(cond, state, timeline, relationships)


@register_condition("event")
def eval_event(cond: ActivationCondition, state, timeline: "EventTimeline", relationships) -> bool:
    return ConditionEvaluator.evaluate(cond, state, timeline, relationships)


@register_condition("quest")
def eval_quest(cond: ActivationCondition, state: "WorldState", timeline, relationships) -> bool:
    return ConditionEvaluator.evaluate(cond, state, timeline, relationships)


def _compare(actual: int, operator: str, target: int) -> bool:
    if operator == "==":
        return actual == target
    if operator == "!=":
        return actual != target
    if operator == ">":
        return actual > target
    if operator == "<":
        return actual < target
    if operator == ">=":
        return actual >= target
    if operator == "<=":
        return actual <= target
    return False


@register_condition("quest_count")
def eval_quest_count(cond: ActivationCondition, state: "WorldState", timeline, relationships) -> bool:
    if cond.check is None or cond.operator is None or cond.value is None:
        return False
    count = sum(1 for q in state.quests.values() if q.get("status") == cond.check)
    return _compare(count, cond.operator, cond.value)


@register_condition("turn_count")
def eval_turn_count(cond: ActivationCondition, state: "WorldState", timeline, relationships) -> bool:
    if cond.operator is None or cond.value is None:
        return False
    return _compare(state.turn, cond.operator, cond.value)
