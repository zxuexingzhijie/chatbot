from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from tavern.world.skills import ActivationCondition, ConditionEvaluator

from tavern.world.memory import EventTimeline, RelationshipGraph

if TYPE_CHECKING:
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


import re as _re

_REL_PATTERN = _re.compile(
    r"^relationship:(\w+)\s*(==|!=|>=|<=|>|<)\s*(-?\d+)$"
)


def parse_condition_str(condition_str: str) -> ActivationCondition:
    if not condition_str or ":" not in condition_str:
        raise ValueError(f"Cannot parse condition string: {condition_str!r}")

    if condition_str.startswith("event_exists:"):
        event_id = condition_str.split(":", 1)[1].strip()
        return ActivationCondition(type="event", event_id=event_id, check="exists")

    if condition_str.startswith("event_not_exists:"):
        event_id = condition_str.split(":", 1)[1].strip()
        return ActivationCondition(type="event", event_id=event_id, check="not_exists")

    cond_type, _, rest = condition_str.partition(":")
    rest = rest.strip()

    if cond_type == "event":
        return ActivationCondition(type="event", event_id=rest, check="exists")

    if cond_type == "relationship":
        m = _REL_PATTERN.match(condition_str)
        if not m:
            raise ValueError(f"Cannot parse relationship condition: {condition_str!r}")
        target, op, val = m.group(1), m.group(2), int(m.group(3))
        return ActivationCondition(
            type="relationship", source="player", target=target,
            operator=op, value=val,
        )

    if cond_type == "inventory":
        return ActivationCondition(type="inventory", event_id=rest)

    if cond_type == "quest":
        parts = rest.split(":", 1)
        if len(parts) == 2:
            return ActivationCondition(type="quest", event_id=parts[0], check=parts[1])
        return ActivationCondition(type="quest", event_id=rest)

    if cond_type == "location":
        return ActivationCondition(type="location", event_id=rest)

    raise ValueError(f"Cannot parse condition string: {condition_str!r}")


def evaluate_condition_str(
    condition_str: str,
    state: "WorldState",
    timeline: EventTimeline,
    relationships: RelationshipGraph,
) -> bool:
    cond = parse_condition_str(condition_str)
    evaluator = CONDITION_REGISTRY.get(cond.type)
    if evaluator is None:
        logger.warning("No evaluator for condition type: %s", cond.type)
        return False
    return evaluator(cond, state, timeline, relationships)
